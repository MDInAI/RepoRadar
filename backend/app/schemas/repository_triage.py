from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import RepositoryTriageExplanationKind, RepositoryTriageStatus


class RepositoryTriageExplanationResponse(BaseModel):
    kind: RepositoryTriageExplanationKind
    summary: str
    matched_include_rules: list[str] = Field(default_factory=list)
    matched_exclude_rules: list[str] = Field(default_factory=list)
    explained_at: datetime


class RepositoryTriageResponse(BaseModel):
    triage_status: RepositoryTriageStatus
    triaged_at: datetime | None = None
    explanation: RepositoryTriageExplanationResponse | None = None
