from pathlib import Path

from core import router
from core.router import FrameworkPack, detect_framework, get_framework_pack, resolve_frameworks


def test_detect_framework_prefers_explicit_hint() -> None:
    assert detect_framework(repo_files=["package.json"], framework_hint="qa") == "qa"


def test_get_framework_pack_supports_domain_packs(monkeypatch) -> None:
    monkeypatch.setattr(router, "get_standards_content", lambda framework: f"{framework} rules")
    pack = get_framework_pack("qa")
    assert isinstance(pack, FrameworkPack)
    assert pack.name == "qa"
    assert pack.module_name == "generic_agent"
    assert pack.prompt_dir == Path(__file__).resolve().parents[1] / "domains" / "qa" / "prompts"


def test_get_framework_pack_supports_database_packs(monkeypatch) -> None:
    monkeypatch.setattr(router, "get_standards_content", lambda framework: f"{framework} rules")
    pack = get_framework_pack("database")
    assert isinstance(pack, FrameworkPack)
    assert pack.name == "database"
    assert pack.module_name == "generic_agent"
    assert pack.prompt_dir == Path(__file__).resolve().parents[1] / "domains" / "database" / "prompts"


def test_resolve_frameworks_supports_multiple_domains() -> None:
    assert resolve_frameworks(repo_files=["package.json", ".csproj"], framework_hint="auto") == ["react", "dotnet"]
