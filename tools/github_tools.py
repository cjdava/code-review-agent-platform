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


@tool(context=True)
def get_pr_files(owner: str, repo: str, pr_number: int, tool_context: ToolContext) -> dict[str, Any]:
    """Get changed files for a pull request."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
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
        return _error(str(exc))

    return _success({"diff": response.text[:8000]})


@tool(context=True)
def get_repo_files(owner: str, repo: str, tool_context: ToolContext) -> dict[str, Any]:
    """Get the repository file tree for repository context."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        return _error(str(exc))

    data = response.json()
    files = [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]
    return _success({"files": files[:1000]})


@tool(context=True)
def find_repo_files(owner: str, repo: str, contains: str, suffix: str = "", limit: int = 200, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Find repository files by case-insensitive name/path matching."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    try:
        response = requests.get(url, headers=_github_headers(), timeout=settings.request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
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
        return _error(str(exc))

    data = response.json()
    encoded_content = data.get("content", "")
    normalized_limit = max(1, min(max_chars, 50000))
    try:
        decoded_content = base64.b64decode(encoded_content).decode("utf-8", errors="replace")
    except binascii.Error as exc:
        return _error(f"Failed to decode file content for {path}: {exc}")

    return _success({"path": path, "ref": ref, "content": decoded_content[:normalized_limit], "truncated": len(decoded_content) > normalized_limit})
