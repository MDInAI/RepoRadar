from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.repository import AgentMemorySegment

logger = logging.getLogger(__name__)


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
        from app.models.repository import _utcnow

        logger.debug(
            f"Writing memory segment: context_id={obsession_context_id}, "
            f"segment_key='{segment_key}', content_type={content_type}, size={len(content)}"
        )

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
                'updated_at': _utcnow(),
            }
        ).returning(AgentMemorySegment)

        result = self._session.execute(stmt)
        segment = result.scalar_one()
        self._session.flush()

        logger.debug(f"Memory segment written: id={segment.id}")

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
        logger.debug(f"Reading memory segment: context_id={obsession_context_id}, segment_key='{segment_key}'")

        stmt = select(AgentMemorySegment).where(
            AgentMemorySegment.obsession_context_id == obsession_context_id,
            AgentMemorySegment.segment_key == segment_key,
        )
        segment = self._session.execute(stmt).scalar_one_or_none()

        if not segment:
            logger.debug(f"Memory segment not found: context_id={obsession_context_id}, segment_key='{segment_key}'")
            return None

        logger.debug(f"Memory segment found: id={segment.id}")
        return MemorySegmentRecord(
            id=segment.id,
            obsession_context_id=segment.obsession_context_id,
            segment_key=segment.segment_key,
            content=segment.content,
            content_type=segment.content_type,
            created_at=segment.created_at,
            updated_at=segment.updated_at,
        )

    def list_segments(
        self,
        obsession_context_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MemorySegmentRecord]:
        logger.debug(f"Listing memory segments: context_id={obsession_context_id}, limit={limit}, offset={offset}")

        stmt = select(AgentMemorySegment).where(
            AgentMemorySegment.obsession_context_id == obsession_context_id
        ).order_by(AgentMemorySegment.segment_key).offset(offset)

        if limit is not None:
            stmt = stmt.limit(limit)

        segments = self._session.execute(stmt).scalars().all()

        logger.debug(f"Found {len(segments)} memory segments for context_id={obsession_context_id}")

        return [
            MemorySegmentRecord(
                id=seg.id,
                obsession_context_id=seg.obsession_context_id,
                segment_key=seg.segment_key,
                content=seg.content,
                content_type=seg.content_type,
                created_at=seg.created_at,
                updated_at=seg.updated_at,
            )
            for seg in segments
        ]

    def delete_segment(
        self,
        obsession_context_id: int,
        segment_key: str,
    ) -> bool:
        logger.debug(f"Deleting memory segment: context_id={obsession_context_id}, segment_key='{segment_key}'")

        stmt = select(AgentMemorySegment).where(
            AgentMemorySegment.obsession_context_id == obsession_context_id,
            AgentMemorySegment.segment_key == segment_key,
        )
        segment = self._session.execute(stmt).scalar_one_or_none()

        if not segment:
            logger.debug(f"Memory segment not found for deletion: context_id={obsession_context_id}, segment_key='{segment_key}'")
            return False

        self._session.delete(segment)
        self._session.flush()
        logger.debug(f"Memory segment deleted: id={segment.id}")
        return True
