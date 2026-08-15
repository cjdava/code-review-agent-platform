from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    owner: str
    repo: str
    pr_number: int = Field(ge=1)
    framework: str = "auto"
    callback_url: str | None = None
    run_id: str | None = None
