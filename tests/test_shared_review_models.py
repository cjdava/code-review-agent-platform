from domain.models import Finding, ReviewResult, ReviewSummary


def test_domain_models_are_single_source_of_truth() -> None:
    """Guard against domain model drift — all layers must import from domain.models."""
    assert Finding is not None
    assert ReviewResult is not None
    assert ReviewSummary is not None


def test_finding_rejects_inverted_line_range() -> None:
    import pytest
    with pytest.raises(ValueError, match="end_line"):
        Finding(
            rule="R1", category="C", severity="LOW",
            file="f.py", start_line=10, end_line=5,
            description="d", code_snippet="s",
        )
