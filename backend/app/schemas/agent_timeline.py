from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class BackfillTimelineResponse(BaseModel):
    agent_name: str = "backfill"
    oldest_date_in_window: date
    newest_boundary_exclusive: date
    current_cursor: datetime | None = None
    next_page: int
    exhausted: bool
    resume_required: bool
    last_checkpointed_at: datetime | None = None
    summary: str
    notes: list[str]


class BackfillTimelineUpdateRequest(BaseModel):
    oldest_date_in_window: date
    newest_boundary_exclusive: date


class BackfillTimelineUpdateResponse(BackfillTimelineResponse):
    message: str
