from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class IdeaFamilyResponse(BaseModel):
    id: int
    title: str
    description: str | None
    member_count: int
    created_at: datetime
    updated_at: datetime


class IdeaFamilyDetailResponse(BaseModel):
    id: int
    title: str
    description: str | None
    member_count: int
    member_repository_ids: list[int]
    created_at: datetime
    updated_at: datetime


class IdeaFamilyCreateRequest(BaseModel):
    title: str = Field(max_length=200)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty")
        return stripped


class IdeaFamilyUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty")
        return stripped


class IdeaFamilyMembershipRequest(BaseModel):
    github_repository_id: int
