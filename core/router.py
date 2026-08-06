from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.standards_loader import get_standards_content


@dataclass
class FrameworkPack:
    name: str
    module_name: str
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
    return frameworks or ["dotnet"]


def get_framework_pack(framework: str) -> FrameworkPack:
    framework_name = framework.lower()
    if framework_name in {"python", "py"}:
        return FrameworkPack(
            name="python",
            module_name="generic_agent",
            prompt_dir=Path(__file__).resolve().parent.parent / "domains" / "python" / "prompts",
            standards_content=get_standards_content("python"),
        )
    if framework_name in {"react", "js", "ts"}:
        return FrameworkPack(
            name="react",
            module_name="generic_agent",
            prompt_dir=Path(__file__).resolve().parent.parent / "domains" / "react" / "prompts",
            standards_content=get_standards_content("react"),
        )
    if framework_name in {"qa", "quality-assurance"}:
        return FrameworkPack(
            name="qa",
            module_name="generic_agent",
            prompt_dir=Path(__file__).resolve().parent.parent / "domains" / "qa" / "prompts",
            standards_content=get_standards_content("qa"),
        )
    if framework_name in {"database", "db", "mssql"}:
        return FrameworkPack(
            name="database",
            module_name="generic_agent",
            prompt_dir=Path(__file__).resolve().parent.parent / "domains" / "database" / "prompts",
            standards_content=get_standards_content("database"),
        )
    return FrameworkPack(
        name="dotnet",
        module_name="generic_agent",
        prompt_dir=Path(__file__).resolve().parent.parent / "domains" / "dotnet" / "prompts",
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
