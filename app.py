from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.router import combine_standards, get_framework_pack, get_framework_packs, resolve_frameworks_for_repo
from generic_agent import run_agent
from models import Finding as ReviewFinding, ReviewResult, ReviewSummary

app = FastAPI(title="Code Review Agent Platform", version="0.1.0")


class ReviewRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int = Field(ge=1)
    framework: str = "auto"
    callback_url: str | None = None
    run_id: str | None = None


@app.post("/reviews", response_model=ReviewResult)
def create_review(request: ReviewRequest) -> ReviewResult:
    run_id = request.run_id or f"review-{request.pr_number}"

    frameworks = resolve_frameworks_for_repo(request.owner, request.repo, framework_hint=request.framework)
    packs = get_framework_packs(frameworks)
    primary_pack = packs[0] if packs else get_framework_pack("dotnet")

    try:
        result = run_agent(
            request.owner,
            request.repo,
            request.pr_number,
            run_id=run_id,
            framework=frameworks[0],
            standards_content=combine_standards(packs),
            prompt_dir=primary_pack.prompt_dir,
            review_domain=primary_pack.name,
        )
        return ReviewResult(
            run_id=result.run_id,
            pr_number=result.pr_number,
            status=result.status,
            summary=ReviewSummary(
                total_findings=result.summary.total_findings,
                high_or_critical=result.summary.high_or_critical,
            ),
            findings=[
                ReviewFinding(
                    rule=f.rule,
                    category=f.category,
                    severity=f.severity,
                    file=f.file,
                    start_line=f.start_line,
                    end_line=f.end_line,
                    description=f.description,
                    code_snippet=f.code_snippet,
                )
                for f in result.findings
            ],
        )
    except Exception as exc:  # pragma: no cover - simple bridge for now
        raise HTTPException(status_code=500, detail=str(exc)) from exc
