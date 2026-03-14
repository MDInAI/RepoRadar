from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, or_, func, cast, String, exists, literal_column
from sqlalchemy.orm import Session

from app.models.repository import SynthesisRun, SynthesisRunType, SynthesisRunStatus


@dataclass(frozen=True)
class SynthesisRunRecord:
    id: int
    idea_family_id: int | None
    obsession_context_id: int | None
    run_type: str
    status: str
    input_repository_ids: list[int]
    output_text: str | None
    title: str | None
    summary: str | None
    key_insights: list[str] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class SynthesisRepository:
    def __init__(self, session: Session):
        self._session = session

    def create_run(
        self, idea_family_id: int | None, run_type: str, repository_ids: list[int], obsession_context_id: int | None = None
    ) -> SynthesisRunRecord:
        run = SynthesisRun(
            idea_family_id=idea_family_id,
            run_type=SynthesisRunType(run_type),
            input_repository_ids=repository_ids,
            obsession_context_id=obsession_context_id,
        )
        self._session.add(run)
        self._session.flush()
        return self._to_record(run)

    def get_run(self, run_id: int) -> SynthesisRunRecord | None:
        run = self._session.get(SynthesisRun, run_id)
        if not run:
            return None
        return self._to_record(run)

    def list_runs(
        self,
        idea_family_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        repository_id: int | None = None,
        obsession_context_id: int | None = None,
    ) -> list[SynthesisRunRecord]:
        stmt = select(SynthesisRun).order_by(SynthesisRun.created_at.desc())

        if idea_family_id is not None:
            stmt = stmt.where(SynthesisRun.idea_family_id == idea_family_id)

        if obsession_context_id is not None:
            stmt = stmt.where(SynthesisRun.obsession_context_id == obsession_context_id)

        if status is not None:
            stmt = stmt.where(SynthesisRun.status == SynthesisRunStatus(status))

        if search is not None:
            query = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(SynthesisRun.title).like(query),
                    func.lower(SynthesisRun.summary).like(query),
                    func.lower(cast(SynthesisRun.key_insights, String)).like(query),
                )
            )

        if date_from is not None:
            stmt = stmt.where(SynthesisRun.created_at >= date_from)

        if date_to is not None:
            stmt = stmt.where(SynthesisRun.created_at <= date_to)

        if repository_id is not None:
            # Use SQLite json_each to check array membership
            from sqlalchemy import exists, literal_column
            subq = select(literal_column("1")).select_from(
                func.json_each(SynthesisRun.input_repository_ids)
            ).where(literal_column("value") == repository_id)
            stmt = stmt.where(exists(subq).correlate(SynthesisRun))

        runs = self._session.execute(stmt).scalars().all()
        return [self._to_record(run) for run in runs]

    def update_run_status(
        self,
        run_id: int,
        status: str,
        output: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        key_insights: list[str] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> SynthesisRunRecord:
        run = self._session.get(SynthesisRun, run_id)
        if not run:
            raise ValueError(f"Synthesis run {run_id} not found")

        run.status = SynthesisRunStatus(status)
        if output is not None:
            run.output_text = output
        if title is not None:
            run.title = title
        if summary is not None:
            run.summary = summary
        if key_insights is not None:
            run.key_insights = key_insights
        if error is not None:
            run.error_message = error
        if started_at is not None:
            run.started_at = started_at
        if completed_at is not None:
            run.completed_at = completed_at

        self._session.flush()
        return self._to_record(run)

    def _to_record(self, run: SynthesisRun) -> SynthesisRunRecord:
        return SynthesisRunRecord(
            id=run.id,
            idea_family_id=run.idea_family_id,
            obsession_context_id=run.obsession_context_id,
            run_type=run.run_type.value,
            status=run.status.value,
            input_repository_ids=run.input_repository_ids,
            output_text=run.output_text,
            title=run.title,
            summary=run.summary,
            key_insights=run.key_insights,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )
