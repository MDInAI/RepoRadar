from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MemorySegmentResponse(BaseModel):
    id: int
    segment_key: str
    content: str
    content_type: str
    created_at: datetime
    updated_at: datetime


class MemorySegmentWriteRequest(BaseModel):
    segment_key: str = Field(max_length=100)
    content: str
    content_type: Literal["markdown", "json"] = "markdown"

    @field_validator("segment_key")
    @classmethod
    def validate_segment_key(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("segment_key cannot be empty")
        import re
        if not re.match(r'^[a-zA-Z0-9_.-]+$', v):
            raise ValueError("segment_key must contain only alphanumeric characters, underscores, hyphens, and dots")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content cannot be empty")
        if len(v.encode('utf-8')) > 51200:  # 50KB in bytes
            raise ValueError("content exceeds 50KB limit")
        return v
