from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.repository import ObsessionContext, SynthesisRun, AgentMemorySegment


def _enum_to_str(value):
    """Convert enum to string, handling both enum and string values."""
    return value.value if hasattr(value, 'value') else value


@dataclass(frozen=True)
class ObsessionContextRecord:
    id: int
    idea_family_id: int | None
    synthesis_run_id: int | None
    title: str
    description: str | None
    status: str
    refresh_policy: str
    last_refresh_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SynthesisRunSummaryRecord:
    id: int
    run_type: str
    status: str
    title: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ObsessionRepository:
    def __init__(self, session: Session):
        self._session = session

    def create_context(
        self,
        title: str,
        description: str | None,
        refresh_policy: str,
        idea_family_id: int | None = None,
        synthesis_run_id: int | None = None,
    ) -> ObsessionContextRecord:
        context = ObsessionContext(
            idea_family_id=idea_family_id,
            synthesis_run_id=synthesis_run_id,
            title=title,
            description=description,
            refresh_policy=refresh_policy,
        )
        self._session.add(context)
        self._session.flush()
        return ObsessionContextRecord(
            id=context.id,
            idea_family_id=context.idea_family_id,
            synthesis_run_id=context.synthesis_run_id,
            title=context.title,
            description=context.description,
            status=_enum_to_str(context.status),
            refresh_policy=_enum_to_str(context.refresh_policy),
            last_refresh_at=context.last_refresh_at,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )

    def get_context(self, context_id: int) -> ObsessionContextRecord | None:
        context = self._session.get(ObsessionContext, context_id)
        if not context:
            return None
        return ObsessionContextRecord(
            id=context.id,
            idea_family_id=context.idea_family_id,
            synthesis_run_id=context.synthesis_run_id,
            title=context.title,
            description=context.description,
            status=_enum_to_str(context.status),
            refresh_policy=_enum_to_str(context.refresh_policy),
            last_refresh_at=context.last_refresh_at,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )

    def list_contexts(
        self, idea_family_id: int | None, status: str | None
    ) -> list[ObsessionContextRecord]:
        stmt = select(ObsessionContext)
        if idea_family_id is not None:
            stmt = stmt.where(ObsessionContext.idea_family_id == idea_family_id)
        if status is not None:
            stmt = stmt.where(ObsessionContext.status == status)
        stmt = stmt.order_by(ObsessionContext.created_at.desc())
        contexts = self._session.execute(stmt).scalars().all()
        return [
            ObsessionContextRecord(
                id=c.id,
                idea_family_id=c.idea_family_id,
                synthesis_run_id=c.synthesis_run_id,
                title=c.title,
                description=c.description,
                status=_enum_to_str(c.status),
                refresh_policy=_enum_to_str(c.refresh_policy),
                last_refresh_at=c.last_refresh_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in contexts
        ]

    def update_context(
        self,
        context_id: int,
        title: str | None,
        description: str | None | object,
        status: str | None,
        refresh_policy: str | None,
    ) -> ObsessionContextRecord:
        context = self._session.get(ObsessionContext, context_id)
        if not context:
            from app.core.errors import AppError

            raise AppError(
                message=f"Obsession context {context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        if title is not None:
            context.title = title
        if description is not ...:
            context.description = description
        if status is not None:
            context.status = status
        if refresh_policy is not None:
            context.refresh_policy = refresh_policy

        context.updated_at = datetime.now(timezone.utc)
        self._session.flush()

        return ObsessionContextRecord(
            id=context.id,
            idea_family_id=context.idea_family_id,
            synthesis_run_id=context.synthesis_run_id,
            title=context.title,
            description=context.description,
            status=_enum_to_str(context.status),
            refresh_policy=_enum_to_str(context.refresh_policy),
            last_refresh_at=context.last_refresh_at,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )

    def update_last_refresh(self, context_id: int) -> ObsessionContextRecord:
        context = self._session.get(ObsessionContext, context_id)
        if not context:
            from app.core.errors import AppError

            raise AppError(
                message=f"Obsession context {context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        context.last_refresh_at = datetime.now(timezone.utc)
        context.updated_at = datetime.now(timezone.utc)
        self._session.flush()

        return ObsessionContextRecord(
            id=context.id,
            idea_family_id=context.idea_family_id,
            synthesis_run_id=context.synthesis_run_id,
            title=context.title,
            description=context.description,
            status=_enum_to_str(context.status),
            refresh_policy=_enum_to_str(context.refresh_policy),
            last_refresh_at=context.last_refresh_at,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )

    def get_synthesis_run_count(self, context_id: int) -> int:
        stmt = select(func.count()).select_from(SynthesisRun).where(SynthesisRun.obsession_context_id == context_id)
        return self._session.execute(stmt).scalar_one()

    def get_synthesis_run_counts(self, context_ids: list[int]) -> dict[int, int]:
        """Batch load synthesis run counts for multiple contexts to avoid N+1 queries."""
        if not context_ids:
            return {}
        stmt = (
            select(SynthesisRun.obsession_context_id, func.count())
            .where(SynthesisRun.obsession_context_id.in_(context_ids))
            .group_by(SynthesisRun.obsession_context_id)
        )
        results = self._session.execute(stmt).all()
        return {context_id: count for context_id, count in results}

    def get_synthesis_runs(self, context_id: int) -> list[SynthesisRunSummaryRecord]:
        stmt = (
            select(SynthesisRun)
            .where(SynthesisRun.obsession_context_id == context_id)
            .order_by(SynthesisRun.created_at.desc())
        )
        runs = self._session.execute(stmt).scalars().all()
        return [
            SynthesisRunSummaryRecord(
                id=r.id,
                run_type=_enum_to_str(r.run_type),
                status=_enum_to_str(r.status),
                title=r.title,
                started_at=r.started_at,
                completed_at=r.completed_at,
                created_at=r.created_at,
            )
            for r in runs
        ]

    def get_memory_segment_count(self, context_id: int) -> int:
        stmt = select(func.count()).select_from(AgentMemorySegment).where(AgentMemorySegment.obsession_context_id == context_id)
        return self._session.execute(stmt).scalar_one()
