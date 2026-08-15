import logging

from application.framework_resolver import combine_standards, get_framework_pack, get_framework_packs, resolve_frameworks_for_repo
from domain.models import ReviewResult
from infrastructure.agent_runner import run_agent

logger = logging.getLogger(__name__)


def run_review(
    owner: str,
    repo: str,
    pr_number: int,
    run_id: str = "LOCAL_RUN",
    framework_hint: str = "auto",
) -> ReviewResult:
    frameworks = resolve_frameworks_for_repo(owner, repo, framework_hint=framework_hint)
    logger.info("Resolved frameworks=%s for %s/%s (hint=%s)", frameworks, owner, repo, framework_hint)
    packs = get_framework_packs(frameworks)
    primary_pack = packs[0] if packs else get_framework_pack("dotnet")
    logger.info("Using primary pack=%s", primary_pack.name)
    return run_agent(
        owner,
        repo,
        pr_number,
        run_id=run_id,
        framework=frameworks[0],
        standards_content=combine_standards(packs),
        prompt_dir=primary_pack.prompt_dir,
        review_domain=primary_pack.name,
    )
