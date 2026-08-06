import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from strands import Agent
from strands.models.openai import OpenAIModel

from config import settings
from tools.github_tools import (
    find_repo_files,
    get_pr_diff,
    get_pr_files,
    get_repo_file_content,
    get_repo_files,
)

DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class Finding(BaseModel):
    rule: str
    category: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    description: str
    code_snippet: str

    @model_validator(mode="after")
    def validate_line_range(self) -> "Finding":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ReviewSummary(BaseModel):
    total_findings: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)


class ReviewResult(BaseModel):
    run_id: str
    pr_number: int
    status: Literal["PASS", "FAIL"]
    summary: ReviewSummary
    findings: list[Finding] = Field(default_factory=list)


def _resolve_prompt_dir(prompt_dir: Path | None = None) -> Path:
    if prompt_dir is not None and prompt_dir.exists():
        return prompt_dir
    return DEFAULT_PROMPTS_DIR


def build_system_prompt(prompt_dir: Path | None = None) -> str:
    resolved_dir = _resolve_prompt_dir(prompt_dir)
    try:
        return (resolved_dir / "system_prompt.md").read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"System prompt file not found: {resolved_dir / 'system_prompt.md'}") from exc


def build_review_prompt(
    owner: str,
    repo: str,
    pr_number: int,
    standards_content: str | None = None,
    prompt_dir: Path | None = None,
) -> str:
    resolved_dir = _resolve_prompt_dir(prompt_dir)
    try:
        template = (resolved_dir / "review_prompt.md").read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Review prompt file not found: {resolved_dir / 'review_prompt.md'}") from exc

    standards_block = f"\n\nStandards:\n{standards_content}" if standards_content else ""
    return template.format(owner=owner, repo=repo, pr_number=pr_number) + standards_block


def build_agent(prompt_dir: Path | None = None, review_domain: str = "generic") -> Agent:
    model = OpenAIModel(
        model_id=settings.openai_model,
        client_args={"api_key": settings.openai_api_key.get_secret_value()},
        params={"temperature": 0, "seed": 42},
    )
    return Agent(
        model=model,
        tools=[
            get_pr_files,
            get_pr_diff,
            get_repo_files,
            find_repo_files,
            get_repo_file_content,
        ],
        system_prompt=build_system_prompt(prompt_dir),
        callback_handler=None,
        load_tools_from_directory=False,
        structured_output_model=ReviewResult,
        name=f"{review_domain}-review-agent",
        description=f"Reviews {review_domain} pull requests against a best-practices checklist.",
    )


def normalize_review_result(result: ReviewResult, run_id: str, pr_number: int) -> ReviewResult:
    unique_findings = {(finding.file, finding.start_line, finding.rule): finding for finding in result.findings}
    findings = sorted(unique_findings.values(), key=lambda finding: (finding.file, finding.start_line, finding.rule))
    high_or_critical = sum(1 for finding in findings if finding.severity in {"HIGH", "CRITICAL"})
    status: Literal["PASS", "FAIL"] = "FAIL" if high_or_critical > 0 else "PASS"

    return ReviewResult(
        run_id=run_id,
        pr_number=pr_number,
        status=status,
        summary=ReviewSummary(total_findings=len(findings), high_or_critical=high_or_critical),
        findings=findings,
    )


def run_agent(
    owner: str,
    repo: str,
    pr_number: int,
    run_id: str = "LOCAL_RUN",
    framework: str | None = None,
    standards_content: str | None = None,
    prompt_dir: Path | None = None,
    review_domain: str | None = None,
) -> ReviewResult:
    review_domain_name = review_domain or framework or "generic"
    logger.info("Starting review owner=%s repo=%s pr=%s model=%s domain=%s", owner, repo, pr_number, settings.openai_model, review_domain_name)
    agent = build_agent(prompt_dir=prompt_dir, review_domain=review_domain_name)
    result = agent(
        build_review_prompt(owner, repo, pr_number, standards_content=standards_content, prompt_dir=prompt_dir),
        structured_output_model=ReviewResult,
    )

    if result.structured_output is None:
        raise ValueError("Agent returned no structured output")

    return normalize_review_result(result.structured_output, run_id, pr_number)
