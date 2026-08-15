import os
from typing import Optional
import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_STANDARDS_REPO = os.getenv(
    "STANDARDS_REPO_URL",
    "https://raw.githubusercontent.com/cjdava/best-practices/main",
)


def get_standards_content(framework: str, standards_repo_url: Optional[str] = None) -> str:
    repo_url = standards_repo_url or DEFAULT_STANDARDS_REPO
    framework_name = framework.lower()

    if framework_name == "python":
        path = "backend/python-standards.md"
    elif framework_name == "react":
        path = "frontend/react/engineering-standards.md"
    elif framework_name in {"qa", "quality-assurance"}:
        path = "qa/playwright-standards.md"
    elif framework_name in {"database", "db", "mssql"}:
        path = "database/mssql-standards.md"
    else:
        path = "backend/dotnet-standards.md"

    url = f"{repo_url.rstrip('/')}/{path}"
    logger.info("Fetching standards content framework=%s url=%s", framework_name, url)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch standards framework=%s url=%s: %s", framework_name, url, exc)
        raise
    return response.text
