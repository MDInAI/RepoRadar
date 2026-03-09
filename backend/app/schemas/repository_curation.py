from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RepositoryCurationResponse(BaseModel):
    is_starred: bool = False
    starred_at: datetime | None = None
    user_tags: list[str] = Field(default_factory=list)


class RepositoryStarRequest(BaseModel):
    starred: bool


class RepositoryUserTagRequest(BaseModel):
    tag_label: str = Field(max_length=100)

    @field_validator("tag_label", mode="before")
    @classmethod
    def _normalize_tag_label(cls, value: str) -> str:
        normalized = value.strip()
        if normalized == "":
            raise ValueError("tag_label must not be blank.")
        return normalized


class RepositoryUserTagResponse(BaseModel):
    tag_label: str
    created_at: datetime
