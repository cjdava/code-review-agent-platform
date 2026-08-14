from pathlib import Path

import requests

from core import router
from core.router import FrameworkPack, detect_framework, get_framework_pack, resolve_frameworks, resolve_frameworks_for_repo


def test_detect_framework_prefers_explicit_hint() -> None:
    assert detect_framework(repo_files=["package.json"], framework_hint="qa") == "qa"


def test_get_framework_pack_supports_domain_packs(monkeypatch) -> None:
    monkeypatch.setattr(router, "get_standards_content", lambda framework: f"{framework} rules")
    pack = get_framework_pack("qa")
    assert isinstance(pack, FrameworkPack)
    assert pack.name == "qa"
    assert pack.prompt_dir == Path(__file__).resolve().parents[1] / "domains" / "qa" / "prompts"


def test_get_framework_pack_supports_database_packs(monkeypatch) -> None:
    monkeypatch.setattr(router, "get_standards_content", lambda framework: f"{framework} rules")
    pack = get_framework_pack("database")
    assert isinstance(pack, FrameworkPack)
    assert pack.name == "database"
    assert pack.prompt_dir == Path(__file__).resolve().parents[1] / "domains" / "database" / "prompts"


def test_resolve_frameworks_supports_multiple_domains() -> None:
    assert resolve_frameworks(repo_files=["package.json", ".csproj"], framework_hint="auto") == ["react", "dotnet"]


def test_resolve_frameworks_detects_qa_from_playwright_config() -> None:
    assert resolve_frameworks(repo_files=["playwright.config.ts", "tests/e2e/login.spec.ts"], framework_hint="auto") == ["qa"]


def test_resolve_frameworks_detects_database_from_sql_files() -> None:
    assert resolve_frameworks(repo_files=["db/migrations/001_init.sql"], framework_hint="auto") == ["database"]


def test_resolve_frameworks_for_repo_skips_fetch_when_hint_given(monkeypatch) -> None:
    monkeypatch.setattr(router, "list_repo_file_paths", lambda owner, repo: (_ for _ in ()).throw(AssertionError("should not fetch")))
    assert resolve_frameworks_for_repo("owner", "repo", framework_hint="qa") == ["qa"]


def test_resolve_frameworks_for_repo_detects_from_real_file_list(monkeypatch) -> None:
    monkeypatch.setattr(router, "list_repo_file_paths", lambda owner, repo: ["src/App.tsx", "package.json"])
    assert resolve_frameworks_for_repo("owner", "repo", framework_hint="auto") == ["react"]


def test_resolve_frameworks_for_repo_falls_back_on_fetch_failure(monkeypatch) -> None:
    def raise_request_exception(owner, repo):
        raise requests.RequestException("offline")

    monkeypatch.setattr(router, "list_repo_file_paths", raise_request_exception)
    assert resolve_frameworks_for_repo("owner", "repo", framework_hint="auto") == ["dotnet"]
