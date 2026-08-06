import requests

from core.standards_loader import get_standards_content


def test_get_standards_content_raises_when_remote_fetch_fails(monkeypatch) -> None:
    def raise_request_exception(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(requests, "get", raise_request_exception)

    try:
        get_standards_content("dotnet", standards_repo_url="https://example.invalid")
    except requests.RequestException as exc:
        assert "offline" in str(exc)
    else:
        raise AssertionError("Expected standards loader to raise on remote fetch failure")
