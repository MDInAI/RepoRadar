from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class SynthesisRunResponse(BaseModel):
    id: int
    idea_family_id: int | None
    obsession_context_id: int | None
    run_type: str
    status: str
    input_repository_ids: list[int]
    output_text: str | None
    title: str | None
    summary: str | None
    key_insights: list[str] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class CombinerTriggerRequest(BaseModel):
    idea_family_id: int | None = None
    repository_ids: list[int] | None = Field(default=None, min_length=2, max_length=3)

    @field_validator("repository_ids")
    @classmethod
    def validate_repo_ids(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and (len(v) < 2 or len(v) > 3):
            raise ValueError("repository_ids must contain 2-3 repositories")
        return v

    def model_post_init(self, __context) -> None:
        if self.idea_family_id is None and self.repository_ids is None:
            raise ValueError("Either idea_family_id or repository_ids must be provided")
        if self.idea_family_id is not None and self.repository_ids is not None:
            raise ValueError("Cannot provide both idea_family_id and repository_ids")
