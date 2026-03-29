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
    idea_search_id: int | None = None
    idea_text: str | None = None
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
    idea_search_id: int | None = None
    idea_text: str | None = None
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
    idea_search_id: int | None = Field(default=None, gt=0)
    idea_text: str | None = Field(default=None, min_length=1, max_length=500)
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

    @field_validator("idea_text")
    @classmethod
    def exactly_one_target(cls, v: str | None, info) -> str | None:
        idea_family_id = info.data.get("idea_family_id")
        synthesis_run_id = info.data.get("synthesis_run_id")
        idea_search_id = info.data.get("idea_search_id")
        targets = sum([
            idea_family_id is not None,
            synthesis_run_id is not None,
            idea_search_id is not None,
            v is not None and v.strip() != "",
        ])
        if targets != 1:
            raise ValueError(
                "exactly one of idea_family_id, synthesis_run_id, idea_search_id, "
                "or idea_text must be provided"
            )
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
