from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

from sqlalchemy import delete, func, text
from sqlmodel import Session, select

from app.models import AgentRun, AgentRunStatus, SystemEvent

logger = logging.getLogger(__name__)

# Default retention: keep 7 days of events and runs.
DEFAULT_EVENT_RETENTION_DAYS = 7
DEFAULT_RUN_RETENTION_DAYS = 7

# Process deletions in batches to avoid loading millions of rows into memory.
_DELETE_BATCH_SIZE = 5_000


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
        event_retention_days: int = DEFAULT_EVENT_RETENTION_DAYS,
        run_retention_days: int = DEFAULT_RUN_RETENTION_DAYS,
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

    def purge_operational_history(
        self,
        *,
        event_retention_days: int = DEFAULT_EVENT_RETENTION_DAYS,
        run_retention_days: int = DEFAULT_RUN_RETENTION_DAYS,
        now: datetime | None = None,
        vacuum: bool = False,
    ) -> dict[str, int]:
        """Fast bulk-delete without exporting to archive files.

        Deletes in batches to keep memory usage constant regardless of table size.
        Use this for routine maintenance; use ``archive_operational_history`` when
        you need the exported JSONL backup.
        """
        effective_now = now or datetime.now(timezone.utc)
        event_cutoff = effective_now - timedelta(days=event_retention_days)
        run_cutoff = effective_now - timedelta(days=run_retention_days)

        events_deleted = self._bulk_delete_system_events(older_than=event_cutoff)
        runs_deleted = self._bulk_delete_agent_runs(older_than=run_cutoff)

        if vacuum and (events_deleted > 0 or runs_deleted > 0):
            try:
                # VACUUM cannot run inside a transaction — use raw connection.
                raw_conn = self.session.get_bind().raw_connection()
                raw_conn.execute("VACUUM")
                raw_conn.close()
                logger.info("VACUUM completed after purging %d events + %d runs.",
                            events_deleted, runs_deleted)
            except Exception:
                logger.warning("VACUUM failed (non-critical).", exc_info=True)

        return {"system_events_deleted": events_deleted, "agent_runs_deleted": runs_deleted}

    # -- Batched bulk delete (no export) ----------------------------------------

    def _bulk_delete_system_events(self, *, older_than: datetime) -> int:
        total_deleted = 0
        while True:
            batch_ids = list(
                self.session.exec(
                    select(SystemEvent.id)
                    .where(SystemEvent.created_at < older_than)
                    .order_by(SystemEvent.id)
                    .limit(_DELETE_BATCH_SIZE)
                ).all()
            )
            if not batch_ids:
                break
            self.session.execute(delete(SystemEvent).where(SystemEvent.id.in_(batch_ids)))
            self.session.commit()
            total_deleted += len(batch_ids)
            if len(batch_ids) < _DELETE_BATCH_SIZE:
                break
        return total_deleted

    def _bulk_delete_agent_runs(self, *, older_than: datetime) -> int:
        total_deleted = 0
        while True:
            batch_ids = list(
                self.session.exec(
                    select(AgentRun.id)
                    .where(AgentRun.status != AgentRunStatus.RUNNING)
                    .where(AgentRun.started_at < older_than)
                    .order_by(AgentRun.id)
                    .limit(_DELETE_BATCH_SIZE)
                ).all()
            )
            if not batch_ids:
                break
            self.session.execute(delete(AgentRun).where(AgentRun.id.in_(batch_ids)))
            self.session.commit()
            total_deleted += len(batch_ids)
            if len(batch_ids) < _DELETE_BATCH_SIZE:
                break
        return total_deleted

    # -- Original archive (export + delete) methods -----------------------------

    def archive_system_events(
        self,
        *,
        older_than: datetime,
        limit: int | None = None,
    ) -> ArchiveBatchSummary:
        effective_limit = limit or _DELETE_BATCH_SIZE
        total_exported = 0
        total_deleted = 0
        last_archive_path: Path | None = None

        while True:
            statement = (
                select(SystemEvent)
                .where(SystemEvent.created_at < older_than)
                .order_by(SystemEvent.created_at, SystemEvent.id)
                .limit(effective_limit)
            )
            rows = list(self.session.exec(statement).all())
            if not rows:
                break

            last_archive_path = self._write_archive_file(
                entity_name="system_events",
                rows=rows,
                older_than=older_than,
            )
            row_ids = [row.id for row in rows if row.id is not None]
            self.session.execute(delete(SystemEvent).where(SystemEvent.id.in_(row_ids)))
            self.session.commit()
            total_exported += len(rows)
            total_deleted += len(row_ids)

            if limit is not None or len(rows) < effective_limit:
                break

        return ArchiveBatchSummary(
            entity_name="system_events",
            exported_count=total_exported,
            deleted_count=total_deleted,
            archive_path=last_archive_path,
            older_than=older_than,
        )

    def archive_agent_runs(
        self,
        *,
        older_than: datetime,
        limit: int | None = None,
    ) -> ArchiveBatchSummary:
        effective_limit = limit or _DELETE_BATCH_SIZE
        total_exported = 0
        total_deleted = 0
        last_archive_path: Path | None = None

        while True:
            statement = (
                select(AgentRun)
                .where(AgentRun.status != AgentRunStatus.RUNNING)
                .where(AgentRun.started_at < older_than)
                .order_by(AgentRun.started_at, AgentRun.id)
                .limit(effective_limit)
            )
            rows = list(self.session.exec(statement).all())
            if not rows:
                break

            last_archive_path = self._write_archive_file(
                entity_name="agent_runs",
                rows=rows,
                older_than=older_than,
            )
            row_ids = [row.id for row in rows if row.id is not None]
            self.session.execute(delete(AgentRun).where(AgentRun.id.in_(row_ids)))
            self.session.commit()
            total_exported += len(rows)
            total_deleted += len(row_ids)

            if limit is not None or len(rows) < effective_limit:
                break

        return ArchiveBatchSummary(
            entity_name="agent_runs",
            exported_count=total_exported,
            deleted_count=total_deleted,
            archive_path=last_archive_path,
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
