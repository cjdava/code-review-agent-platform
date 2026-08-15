import base64
import binascii
import logging
from typing import Any

import requests
from strands import ToolContext, tool

from config import settings

logger = logging.getLogger(__name__)


def _github_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {settings.github_token.get_secret_value()}"}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _success(data: Any) -> dict[str, Any]:
    return {"status": "success", "content": [{"json": data}]}


def _error(message: str) -> dict[str, Any]:
    return {"status": "error", "content": [{"json": {"error": message}}]}


def list_repo_file_paths(owner: str, repo: str) -> list[str]:
    """Fetch the repository's blob file paths directly (no tool/agent wrapping)."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
    response.raise_for_status()
    data = response.json()
    return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]


@tool(context=True)
def get_pr_files(owner: str, repo: str, pr_number: int, tool_context: ToolContext) -> dict[str, Any]:
    """Get changed files for a pull request."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("get_pr_files failed owner=%s repo=%s pr=%s: %s", owner, repo, pr_number, exc)
        return _error(str(exc))

    files = response.json()
    summarized_files = [
        {
            "filename": item["filename"],
            "status": item.get("status"),
            "additions": item.get("additions", 0),
            "deletions": item.get("deletions", 0),
            "changes": item.get("changes", 0),
        }
        for item in files
    ]
    return _success({"files": summarized_files})


@tool(context=True)
def get_pr_diff(owner: str, repo: str, pr_number: int, tool_context: ToolContext) -> dict[str, Any]:
    """Get the unified diff for a pull request."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    try:
        response = requests.get(url, headers=_github_headers({"Accept": "application/vnd.github.v3.diff"}), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("get_pr_diff failed owner=%s repo=%s pr=%s: %s", owner, repo, pr_number, exc)
        return _error(str(exc))

    return _success({"diff": response.text[:8000]})


@tool(context=True)
def get_repo_files(owner: str, repo: str, tool_context: ToolContext) -> dict[str, Any]:
    """Get the repository file tree for repository context."""
    try:
        files = list_repo_file_paths(owner, repo)
    except requests.RequestException as exc:
        logger.warning("get_repo_files failed owner=%s repo=%s: %s", owner, repo, exc)
        return _error(str(exc))

    return _success({"files": files[:1000]})


@tool(context=True)
def find_repo_files(owner: str, repo: str, contains: str, suffix: str = "", limit: int = 200, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Find repository files by case-insensitive name/path matching."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("find_repo_files failed owner=%s repo=%s: %s", owner, repo, exc)
        return _error(str(exc))

    data = response.json()
    files = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
    contains_lower = contains.lower().strip()
    suffix_lower = suffix.lower().strip()
    normalized_limit = max(1, min(limit, 1000))
    matches = []
    for path in files:
        lower_path = path.lower()
        if contains_lower and contains_lower not in lower_path:
            continue
        if suffix_lower and not lower_path.endswith(suffix_lower):
            continue
        matches.append(path)
        if len(matches) >= normalized_limit:
            break
    return _success({"contains": contains, "suffix": suffix, "matches": matches, "returned": len(matches)})


@tool(context=True)
def get_repo_file_content(owner: str, repo: str, path: str, ref: str = "HEAD", max_chars: int = 12000, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Get text content for a repository file."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        response = requests.get(url, headers=_github_headers(), params={"ref": ref}, timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("get_repo_file_content failed owner=%s repo=%s path=%s: %s", owner, repo, path, exc)
        return _error(str(exc))

    data = response.json()
    if data.get("encoding") != "base64" or "content" not in data:
        return _error("Unexpected response format from GitHub contents API")

    try:
        raw_bytes = base64.b64decode(data["content"])
    except (binascii.Error, ValueError) as exc:
        return _error(f"Failed to decode file content: {exc}")

    clamped_max = max(1, min(max_chars, 50000))
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _error("File is not valid UTF-8 text")

    return _success({"path": path, "ref": ref, "content": text[:clamped_max], "truncated": len(text) > clamped_max})
