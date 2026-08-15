from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

import requests

from infrastructure.github_client import list_repo_file_paths
from infrastructure.standards_loader import get_standards_content

logger = logging.getLogger(__name__)


@dataclass
class FrameworkPack:
    name: str
    prompt_dir: Path
    standards_content: Optional[str] = None


def detect_framework(repo_files: Optional[list[str]] = None, framework_hint: str = "auto") -> str:
    frameworks = resolve_frameworks(repo_files=repo_files, framework_hint=framework_hint)
    return frameworks[0] if frameworks else "dotnet"


def resolve_frameworks(repo_files: Optional[list[str]] = None, framework_hint: str = "auto") -> list[str]:
    if framework_hint and framework_hint != "auto":
        return [item.strip().lower() for item in framework_hint.split(",") if item.strip()]

    if not repo_files:
        return ["dotnet"]

    normalized = "\n".join(repo_files).lower()
    frameworks: list[str] = []
    if "pyproject.toml" in normalized or "requirements.txt" in normalized or "setup.py" in normalized:
        frameworks.append("python")
    if "package.json" in normalized or "vite.config" in normalized or "next.config" in normalized:
        frameworks.append("react")
    if ".sln" in normalized or ".csproj" in normalized:
        frameworks.append("dotnet")
    if "playwright.config" in normalized or "cypress.config" in normalized or "/e2e/" in normalized:
        frameworks.append("qa")
    if ".sql" in normalized or ".sqlproj" in normalized or "/migrations/" in normalized:
        frameworks.append("database")
    return frameworks or ["dotnet"]


def resolve_frameworks_for_repo(owner: str, repo: str, framework_hint: str = "auto") -> list[str]:
    if framework_hint and framework_hint != "auto":
        return resolve_frameworks(framework_hint=framework_hint)

    try:
        repo_files = list_repo_file_paths(owner, repo)
    except requests.RequestException as exc:
        logger.warning("Failed to fetch file tree for %s/%s (%s); falling back to dotnet", owner, repo, exc)
        return ["dotnet"]

    return resolve_frameworks(repo_files=repo_files, framework_hint="auto")


def get_framework_pack(framework: str) -> FrameworkPack:
    # domains/ lives at <project_root>/domains/, two levels up from this file.
    domains_dir = Path(__file__).resolve().parent.parent / "domains"
    framework_name = framework.lower()
    if framework_name in {"python", "py"}:
        return FrameworkPack(
            name="python",
            prompt_dir=domains_dir / "python" / "prompts",
            standards_content=get_standards_content("python"),
        )
    if framework_name in {"react", "js", "ts"}:
        return FrameworkPack(
            name="react",
            prompt_dir=domains_dir / "react" / "prompts",
            standards_content=get_standards_content("react"),
        )
    if framework_name in {"qa", "quality-assurance"}:
        return FrameworkPack(
            name="qa",
            prompt_dir=domains_dir / "qa" / "prompts",
            standards_content=get_standards_content("qa"),
        )
    if framework_name in {"database", "db", "mssql"}:
        return FrameworkPack(
            name="database",
            prompt_dir=domains_dir / "database" / "prompts",
            standards_content=get_standards_content("database"),
        )
    return FrameworkPack(
        name="dotnet",
        prompt_dir=domains_dir / "dotnet" / "prompts",
        standards_content=get_standards_content("dotnet"),
    )


def get_framework_packs(frameworks: list[str]) -> list[FrameworkPack]:
    return [get_framework_pack(framework) for framework in frameworks if framework]


def combine_standards(packs: list[FrameworkPack]) -> str:
    blocks = []
    for pack in packs:
        if pack.standards_content:
            blocks.append(f"## {pack.name}\n{pack.standards_content}")
    return "\n\n".join(blocks)
