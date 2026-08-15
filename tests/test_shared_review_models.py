from app import ReviewFinding, ReviewResult as ApiReviewResult
from generic_agent import Finding, ReviewResult as AgentReviewResult


def test_review_models_share_the_same_schema() -> None:
    assert ReviewFinding is Finding
    assert ApiReviewResult is AgentReviewResult
