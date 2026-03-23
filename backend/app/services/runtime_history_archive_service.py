from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sqlalchemy import delete
from sqlmodel import Session, select

from app.models import AgentRun, AgentRunStatus, SystemEvent


@dataclass(frozen=True, slots=True)
class ArchiveBatchSummary:
    entity_name: str
    exported_count: int
    deleted_count: int
    archive_path: Path | None
    older_than: datetime


@dataclass(frozen=True, slots=True)
class RuntimeHistoryArchiveResult:
    system_events: ArchiveBatchSummary
    agent_runs: ArchiveBatchSummary


class RuntimeHistoryArchiveService:
    def __init__(self, session: Session, runtime_dir: Path | None) -> None:
        self.session = session
        self.runtime_dir = runtime_dir

    def archive_operational_history(
        self,
        *,
        event_retention_days: int,
        run_retention_days: int,
        event_limit: int | None = None,
        run_limit: int | None = None,
        now: datetime | None = None,
    ) -> RuntimeHistoryArchiveResult:
        effective_now = now or datetime.now(timezone.utc)
        event_cutoff = effective_now - timedelta(days=event_retention_days)
        run_cutoff = effective_now - timedelta(days=run_retention_days)

        system_events = self.archive_system_events(older_than=event_cutoff, limit=event_limit)
        agent_runs = self.archive_agent_runs(older_than=run_cutoff, limit=run_limit)
        return RuntimeHistoryArchiveResult(system_events=system_events, agent_runs=agent_runs)

    def archive_system_events(
        self,
        *,
        older_than: datetime,
        limit: int | None = None,
    ) -> ArchiveBatchSummary:
        statement = (
            select(SystemEvent)
            .where(SystemEvent.created_at < older_than)
            .order_by(SystemEvent.created_at, SystemEvent.id)
        )
        if limit is not None:
            statement = statement.limit(limit)
        rows = list(self.session.exec(statement).all())
        if not rows:
            return ArchiveBatchSummary(
                entity_name="system_events",
                exported_count=0,
                deleted_count=0,
                archive_path=None,
                older_than=older_than,
            )

        archive_path = self._write_archive_file(
            entity_name="system_events",
            rows=rows,
            older_than=older_than,
        )
        row_ids = [row.id for row in rows if row.id is not None]
        self.session.execute(delete(SystemEvent).where(SystemEvent.id.in_(row_ids)))
        self.session.commit()
        return ArchiveBatchSummary(
            entity_name="system_events",
            exported_count=len(rows),
            deleted_count=len(row_ids),
            archive_path=archive_path,
            older_than=older_than,
        )

    def archive_agent_runs(
        self,
        *,
        older_than: datetime,
        limit: int | None = None,
    ) -> ArchiveBatchSummary:
        statement = (
            select(AgentRun)
            .where(AgentRun.status != AgentRunStatus.RUNNING)
            .where(AgentRun.started_at < older_than)
            .order_by(AgentRun.started_at, AgentRun.id)
        )
        if limit is not None:
            statement = statement.limit(limit)
        rows = list(self.session.exec(statement).all())
        if not rows:
            return ArchiveBatchSummary(
                entity_name="agent_runs",
                exported_count=0,
                deleted_count=0,
                archive_path=None,
                older_than=older_than,
            )

        archive_path = self._write_archive_file(
            entity_name="agent_runs",
            rows=rows,
            older_than=older_than,
        )
        row_ids = [row.id for row in rows if row.id is not None]
        self.session.execute(delete(AgentRun).where(AgentRun.id.in_(row_ids)))
        self.session.commit()
        return ArchiveBatchSummary(
            entity_name="agent_runs",
            exported_count=len(rows),
            deleted_count=len(row_ids),
            archive_path=archive_path,
            older_than=older_than,
        )

    def _write_archive_file(
        self,
        *,
        entity_name: str,
        rows: list[SystemEvent | AgentRun],
        older_than: datetime,
    ) -> Path:
        export_dir = self._archive_dir(entity_name)
        export_dir.mkdir(parents=True, exist_ok=True)
        first_timestamp = self._row_timestamp(rows[0])
        last_timestamp = self._row_timestamp(rows[-1])
        filename = (
            f"{entity_name}_"
            f"{first_timestamp:%Y%m%dT%H%M%SZ}_"
            f"{last_timestamp:%Y%m%dT%H%M%SZ}_"
            f"{len(rows)}.jsonl"
        )
        archive_path = export_dir / filename
        with archive_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(
                    json.dumps(
                        {
                            "entity": entity_name,
                            "archived_at": datetime.now(timezone.utc).isoformat(),
                            "older_than": older_than.isoformat(),
                            "record": row.model_dump(mode="json"),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                )
                handle.write("\n")
        return archive_path

    def _archive_dir(self, entity_name: str) -> Path:
        if self.runtime_dir is None:
            raise RuntimeError("AGENTIC_RUNTIME_DIR must be configured to archive operational history.")
        return self.runtime_dir / "data" / "exports" / "operational-history" / entity_name

    @staticmethod
    def _row_timestamp(row: SystemEvent | AgentRun) -> datetime:
        if isinstance(row, SystemEvent):
            return row.created_at
        return row.started_at
