import logging

from fastapi import APIRouter, HTTPException

from api.schemas import ReviewRequest
from application.review_service import run_review
from domain.models import ReviewResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/reviews", response_model=ReviewResult)
def create_review(request: ReviewRequest) -> ReviewResult:
    run_id = request.run_id or f"review-{request.pr_number}"
    logger.info(
        "Received review request owner=%s repo=%s pr=%s framework=%s run_id=%s",
        request.owner, request.repo, request.pr_number, request.framework, run_id,
    )
    try:
        result = run_review(
            request.owner,
            request.repo,
            request.pr_number,
            run_id=run_id,
            framework_hint=request.framework,
        )
        logger.info(
            "Review completed run_id=%s status=%s total_findings=%s",
            result.run_id, result.status, result.summary.total_findings,
        )
        return result
    except Exception as exc:
        logger.exception("Review failed run_id=%s", run_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
