from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Finding(BaseModel):
    rule: str
    category: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    description: str
    code_snippet: str

    @model_validator(mode="after")
    def validate_line_range(self) -> "Finding":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class ReviewSummary(BaseModel):
    total_findings: int = Field(ge=0)
    high_or_critical: int = Field(ge=0)


class ReviewResult(BaseModel):
    run_id: str
    pr_number: int
    status: Literal["PASS", "FAIL"]
    summary: ReviewSummary
    findings: list[Finding] = Field(default_factory=list)
