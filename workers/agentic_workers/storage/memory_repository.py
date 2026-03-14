from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from agentic_workers.storage.backend_models import AgentMemorySegment


@dataclass(frozen=True)
class MemorySegmentRecord:
    id: int
    obsession_context_id: int
    segment_key: str
    content: str
    content_type: str
    created_at: datetime
    updated_at: datetime


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def write_segment(
        self,
        obsession_context_id: int,
        segment_key: str,
        content: str,
        content_type: str,
    ) -> MemorySegmentRecord:
        from datetime import timezone

        stmt = insert(AgentMemorySegment).values(
            obsession_context_id=obsession_context_id,
            segment_key=segment_key,
            content=content,
            content_type=content_type,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=['obsession_context_id', 'segment_key'],
            set_={
                'content': stmt.excluded.content,
                'content_type': stmt.excluded.content_type,
                'updated_at': datetime.now(timezone.utc),
            }
        ).returning(AgentMemorySegment)

        result = self._session.execute(stmt)
        segment = result.scalar_one()
        self._session.flush()

        return MemorySegmentRecord(
            id=segment.id,
            obsession_context_id=segment.obsession_context_id,
            segment_key=segment.segment_key,
            content=segment.content,
            content_type=segment.content_type,
            created_at=segment.created_at,
            updated_at=segment.updated_at,
        )

    def read_segment(
        self,
        obsession_context_id: int,
        segment_key: str,
    ) -> MemorySegmentRecord | None:
        stmt = select(AgentMemorySegment).where(
            AgentMemorySegment.obsession_context_id == obsession_context_id,
            AgentMemorySegment.segment_key == segment_key,
        )
        segment = self._session.execute(stmt).scalar_one_or_none()

        if not segment:
            return None

        return MemorySegmentRecord(
            id=segment.id,
            obsession_context_id=segment.obsession_context_id,
            segment_key=segment.segment_key,
            content=segment.content,
            content_type=segment.content_type,
            created_at=segment.created_at,
            updated_at=segment.updated_at,
        )
