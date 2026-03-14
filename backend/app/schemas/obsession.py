from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class SynthesisRunSummary(BaseModel):
    id: int
    run_type: str
    status: str
    title: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ObsessionContextResponse(BaseModel):
    id: int
    idea_family_id: int | None
    synthesis_run_id: int | None
    title: str
    description: str | None
    status: str
    refresh_policy: str
    last_refresh_at: datetime | None
    synthesis_run_count: int
    created_at: datetime
    updated_at: datetime


class RepositorySummary(BaseModel):
    id: int
    full_name: str
    stars: int


class ObsessionContextDetailResponse(BaseModel):
    id: int
    idea_family_id: int | None
    synthesis_run_id: int | None
    title: str
    description: str | None
    status: str
    refresh_policy: str
    last_refresh_at: datetime | None
    synthesis_runs: list[SynthesisRunSummary]
    family_title: str | None
    repository_count: int
    repositories: list[RepositorySummary]
    memory_segment_count: int
    scope_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ObsessionContextCreateRequest(BaseModel):
    idea_family_id: int | None = Field(default=None, gt=0)
    synthesis_run_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    refresh_policy: str = Field(default="manual")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip()

    @field_validator("refresh_policy")
    @classmethod
    def refresh_policy_valid(cls, v: str) -> str:
        if v not in ("manual", "daily", "weekly"):
            raise ValueError("refresh_policy must be manual, daily, or weekly")
        return v

    @field_validator("synthesis_run_id")
    @classmethod
    def exactly_one_target(cls, v: int | None, info) -> int | None:
        idea_family_id = info.data.get("idea_family_id")
        if (idea_family_id is None and v is None) or (idea_family_id is not None and v is not None):
            raise ValueError("exactly one of idea_family_id or synthesis_run_id must be provided")
        return v


class ObsessionContextUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None | object = None
    status: str | None = None
    refresh_policy: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip() if v is not None else None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "paused", "completed"):
            raise ValueError("status must be active, paused, or completed")
        return v

    @field_validator("refresh_policy")
    @classmethod
    def refresh_policy_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in ("manual", "daily", "weekly"):
            raise ValueError("refresh_policy must be manual, daily, or weekly")
        return v
