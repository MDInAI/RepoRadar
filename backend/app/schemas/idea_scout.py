from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class IdeaSearchCreateRequest(BaseModel):
    idea_text: str = Field(min_length=1, max_length=500)
    direction: str = Field(default="backward")

    @field_validator("idea_text")
    @classmethod
    def idea_text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("idea_text cannot be blank")
        return v.strip()

    @field_validator("direction")
    @classmethod
    def direction_valid(cls, v: str) -> str:
        if v not in ("backward", "forward"):
            raise ValueError("direction must be 'backward' or 'forward'")
        return v


class IdeaSearchUpdateRequest(BaseModel):
    search_queries: list[str] = Field(min_length=1)


class IdeaSearchResponse(BaseModel):
    id: int
    idea_text: str
    search_queries: list[str]
    direction: str
    status: str
    obsession_context_id: int | None
    total_repos_found: int
    analyst_enabled: bool = False
    created_at: datetime
    updated_at: datetime


class IdeaSearchProgressSummary(BaseModel):
    query_index: int
    window_start_date: str
    created_before_boundary: str
    exhausted: bool
    resume_required: bool
    next_page: int
    pages_processed_in_run: int
    last_checkpointed_at: datetime | None
    consecutive_errors: int = 0
    last_error: str | None = None


class IdeaSearchDetailResponse(BaseModel):
    id: int
    idea_text: str
    search_queries: list[str]
    direction: str
    status: str
    obsession_context_id: int | None
    total_repos_found: int
    analyst_enabled: bool = False
    progress: list[IdeaSearchProgressSummary]
    discovery_count: int
    analyzed_count: int = 0
    created_at: datetime
    updated_at: datetime


class DiscoveredRepoResponse(BaseModel):
    github_repository_id: int
    full_name: str
    description: str | None
    stargazers_count: int
    discovered_at: datetime
