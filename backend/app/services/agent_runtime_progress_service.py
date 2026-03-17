from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.config import settings
from app.models import (
    AgentRun,
    AgentRunStatus,
    RepositoryAnalysisStatus,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SynthesisRun,
    SynthesisRunStatus,
    SystemEvent,
)
from app.repositories.intake_runtime_repository import IntakeRuntimeRepository
from app.schemas.agent_event import AgentRuntimeProgress


class AgentRuntimeProgressService:
    def __init__(
        self,
        session: Session,
        *,
        runtime_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.runtime_dir = runtime_dir
        self.intake_runtime_repository = IntakeRuntimeRepository(
            session,
            runtime_dir=runtime_dir,
        )

    def build_for_agent(
        self,
        agent_name: str,
        latest_run: AgentRun | None,
    ) -> AgentRuntimeProgress:
        latest_event = self._load_latest_event(agent_name)
        if agent_name == "firehose":
            return self._build_firehose_progress(latest_run, latest_event)
        if agent_name == "backfill":
            return self._build_backfill_progress(latest_run, latest_event)
        if agent_name == "bouncer":
            return self._build_bouncer_progress(latest_run, latest_event)
        if agent_name == "analyst":
            return self._build_analyst_progress(latest_run, latest_event)
        if agent_name == "combiner":
            return self._build_combiner_progress(latest_run, latest_event)
        if agent_name == "obsession":
            return self._build_generic_progress(
                latest_run,
                latest_event,
                idle_label="No active obsession refresh is running.",
                running_label="Refreshing obsession context.",
                source="agent run state",
            )
        return self._build_generic_progress(
            latest_run,
            latest_event,
            idle_label="No active background work is currently running.",
            running_label="Background run is in progress.",
            source="agent run state",
        )

    def _build_firehose_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
    ) -> AgentRuntimeProgress:
        runtime = self.intake_runtime_repository.load_firehose_runtime()
        total_pages = max(settings.FIREHOSE_PAGES, 1)
        completed_pages = min(runtime.pages_processed_in_run, total_pages)
        progress_percent = min(int(round((completed_pages / total_pages) * 100)), 100)
        current_mode = runtime.active_mode.upper() if runtime.active_mode else "UNKNOWN"
        details = [
            f"Pending discovered repos: {runtime.counts.pending}",
            f"Completed discoveries: {runtime.counts.completed}",
        ]
        if latest_event is not None:
            details.append(latest_event.message)
        return AgentRuntimeProgress(
            status_label="Running current mode" if latest_run and latest_run.status is AgentRunStatus.RUNNING else "Idle",
            current_activity=(
                f"Discovering GitHub repositories in {current_mode} mode."
                if latest_run and latest_run.status is AgentRunStatus.RUNNING
                else "Waiting for the next Firehose cycle."
            ),
            current_target=f"Mode {current_mode}, next page {runtime.next_page}",
            progress_percent=progress_percent,
            completed_count=completed_pages,
            total_count=total_pages,
            remaining_count=max(total_pages - completed_pages, 0),
            unit_label="pages",
            updated_at=runtime.last_checkpointed_at or runtime.run_started_at,
            source="firehose checkpoint + intake queue",
            details=details,
        )

    def _build_backfill_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
    ) -> AgentRuntimeProgress:
        runtime = self.intake_runtime_repository.load_backfill_runtime()
        total_pages = max(settings.BACKFILL_PAGES, 1)
        completed_pages = min(runtime.pages_processed_in_run, total_pages)
        progress_percent = min(int(round((completed_pages / total_pages) * 100)), 100)
        current_window = (
            f"{runtime.window_start_date.isoformat()} to {runtime.created_before_boundary.isoformat()}"
            if runtime.window_start_date is not None and runtime.created_before_boundary is not None
            else "Unknown window"
        )
        details = [
            f"Pending backfill repos: {runtime.counts.pending}",
            f"Completed discoveries: {runtime.counts.completed}",
        ]
        if latest_event is not None:
            details.append(latest_event.message)
        return AgentRuntimeProgress(
            status_label="Running window" if latest_run and latest_run.status is AgentRunStatus.RUNNING else "Idle",
            current_activity=(
                "Discovering older repositories in the active backfill window."
                if latest_run and latest_run.status is AgentRunStatus.RUNNING
                else "Waiting for the next Backfill cycle."
            ),
            current_target=f"{current_window} · next page {runtime.next_page}",
            progress_percent=progress_percent,
            completed_count=completed_pages,
            total_count=total_pages,
            remaining_count=max(total_pages - completed_pages, 0),
            unit_label="pages",
            updated_at=runtime.last_checkpointed_at,
            source="backfill checkpoint + intake queue",
            details=details,
        )

    def _build_bouncer_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
    ) -> AgentRuntimeProgress:
        snapshot = self._load_progress_snapshot("bouncer")
        queue_pending = self._count_repositories(
            RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING,
            RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING,
        )
        queue_in_progress = self._count_repositories(
            RepositoryIntake.queue_status == RepositoryQueueStatus.IN_PROGRESS,
            RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING,
        )
        details = [
            f"Pending triage queue: {queue_pending}",
            f"In-flight triage records: {queue_in_progress}",
        ]
        if latest_event is not None:
            details.append(latest_event.message)
        return self._build_snapshot_or_queue_progress(
            latest_run=latest_run,
            snapshot=snapshot,
            running_label="Triaging pending repositories.",
            idle_label="Waiting for pending repositories that need triage.",
            current_target_fallback=(
                f"{queue_pending} repos pending triage"
                if queue_pending > 0
                else "No repositories waiting for triage"
            ),
            source_fallback="triage queue snapshot",
            details=details,
        )

    def _build_analyst_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
    ) -> AgentRuntimeProgress:
        snapshot = self._load_progress_snapshot("analyst")
        accepted_total = self._count_repositories(
            RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
        )
        pending = self._count_repositories(
            RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
            RepositoryIntake.analysis_status == RepositoryAnalysisStatus.PENDING,
        )
        completed = self._count_repositories(
            RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
            RepositoryIntake.analysis_status == RepositoryAnalysisStatus.COMPLETED,
        )
        in_progress = self._count_repositories(
            RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
            RepositoryIntake.analysis_status == RepositoryAnalysisStatus.IN_PROGRESS,
        )
        failed = self._count_repositories(
            RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED,
            RepositoryIntake.analysis_status == RepositoryAnalysisStatus.FAILED,
        )
        details = [
            f"Pending analysis: {pending}",
            f"Repos currently marked in progress: {in_progress}",
            f"Failed analyses awaiting retry: {failed}",
        ]
        if latest_event is not None:
            details.append(latest_event.message)
        return self._build_snapshot_or_queue_progress(
            latest_run=latest_run,
            snapshot=snapshot,
            running_label="Analyzing accepted repositories.",
            idle_label="Waiting for accepted repositories that need analysis.",
            current_target_fallback=(
                f"{pending + in_progress + failed} repos still need analysis work"
                if (pending + in_progress + failed) > 0
                else "No accepted repositories are waiting for analysis"
            ),
            source_fallback="analysis queue snapshot",
            details=details,
            primary_counts_label="Processed in this Gemini refresh run",
            secondary_counts_label="Already analyzed across accepted repos",
            secondary_completed_count=completed,
            secondary_total_count=accepted_total,
            secondary_remaining_count=pending + in_progress + failed,
            secondary_unit_label="repos",
        )

    def _build_combiner_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
    ) -> AgentRuntimeProgress:
        snapshot = self._load_progress_snapshot("combiner")
        pending_runs = self.session.exec(
            select(func.count())
            .select_from(SynthesisRun)
            .where(SynthesisRun.status == SynthesisRunStatus.PENDING)
            .where(SynthesisRun.run_type == "combiner")
        ).one()
        details = [f"Pending combiner runs: {int(pending_runs or 0)}"]
        if latest_event is not None:
            details.append(latest_event.message)
        return self._build_snapshot_or_queue_progress(
            latest_run=latest_run,
            snapshot=snapshot,
            running_label="Building a synthesis from queued repositories.",
            idle_label="Waiting for a synthesis run to be queued.",
            current_target_fallback=(
                f"{int(pending_runs or 0)} synthesis runs queued"
                if int(pending_runs or 0) > 0
                else "No synthesis runs are queued"
            ),
            source_fallback="combiner run snapshot",
            details=details,
        )

    def _build_generic_progress(
        self,
        latest_run: AgentRun | None,
        latest_event: SystemEvent | None,
        *,
        idle_label: str,
        running_label: str,
        source: str,
    ) -> AgentRuntimeProgress:
        details = [latest_event.message] if latest_event is not None else []
        is_running = latest_run is not None and latest_run.status is AgentRunStatus.RUNNING
        return AgentRuntimeProgress(
            status_label="Running" if is_running else "Idle",
            current_activity=running_label if is_running else idle_label,
            current_target=None,
            progress_percent=None,
            completed_count=latest_run.items_processed if latest_run is not None else None,
            total_count=None,
            remaining_count=None,
            unit_label="items" if latest_run is not None and latest_run.items_processed is not None else None,
            updated_at=(
                latest_event.created_at
                if latest_event is not None
                else latest_run.started_at if latest_run is not None else None
            ),
            source=source,
            details=details,
        )

    def _build_snapshot_or_queue_progress(
        self,
        *,
        latest_run: AgentRun | None,
        snapshot: dict[str, object] | None,
        running_label: str,
        idle_label: str,
        current_target_fallback: str,
        source_fallback: str,
        details: list[str],
        primary_counts_label: str | None = None,
        secondary_counts_label: str | None = None,
        secondary_completed_count: int | None = None,
        secondary_total_count: int | None = None,
        secondary_remaining_count: int | None = None,
        secondary_unit_label: str | None = None,
    ) -> AgentRuntimeProgress:
        is_running = latest_run is not None and latest_run.status is AgentRunStatus.RUNNING
        if snapshot is not None:
            snapshot_updated_at = self._parse_datetime(snapshot.get("generated_at"))
            snapshot_target = self._to_optional_str(snapshot.get("current_target"))
            if self._snapshot_is_stale_for_latest_run(
                snapshot_updated_at=snapshot_updated_at,
                latest_run=latest_run,
            ):
                snapshot = None
            else:
                completed_count = self._to_int(snapshot.get("completed_count"))
                total_count = self._to_int(snapshot.get("total_count"))
                remaining_count = self._to_int(snapshot.get("remaining_count"))
                progress_percent = self._to_int(snapshot.get("progress_percent"))
                snapshot_details = snapshot.get("details")
                return AgentRuntimeProgress(
                    status_label=(
                        str(snapshot.get("status_label") or "Running")
                        if is_running
                        else "Waiting"
                    ),
                    current_activity=(
                        str(snapshot.get("current_activity") or running_label)
                        if is_running
                        else idle_label
                    ),
                    current_target=(
                        snapshot_target
                        if is_running
                        else f"Resume checkpoint: {snapshot_target}"
                        if snapshot_target is not None
                        else current_target_fallback
                    ),
                    progress_percent=progress_percent,
                    primary_counts_label=primary_counts_label,
                    completed_count=completed_count,
                    total_count=total_count,
                    remaining_count=remaining_count,
                    unit_label=self._to_optional_str(snapshot.get("unit_label")),
                    secondary_counts_label=secondary_counts_label,
                    secondary_completed_count=secondary_completed_count,
                    secondary_total_count=secondary_total_count,
                    secondary_remaining_count=secondary_remaining_count,
                    secondary_unit_label=secondary_unit_label,
                    updated_at=snapshot_updated_at,
                    source=self._to_optional_str(snapshot.get("source")) or source_fallback,
                    details=[
                        *details,
                        *[
                            item
                            for item in (snapshot_details if isinstance(snapshot_details, list) else [])
                            if isinstance(item, str)
                        ],
                    ],
                )

        return AgentRuntimeProgress(
            status_label="Running" if is_running else "Idle",
            current_activity=running_label if is_running else idle_label,
            current_target=current_target_fallback,
            progress_percent=None,
            primary_counts_label=primary_counts_label,
            completed_count=latest_run.items_processed if latest_run is not None else None,
            total_count=None,
            remaining_count=None,
            unit_label="repos" if latest_run is not None else None,
            secondary_counts_label=secondary_counts_label,
            secondary_completed_count=secondary_completed_count,
            secondary_total_count=secondary_total_count,
            secondary_remaining_count=secondary_remaining_count,
            secondary_unit_label=secondary_unit_label,
            updated_at=latest_run.started_at if latest_run is not None else None,
            source=source_fallback,
            details=details,
        )

    @staticmethod
    def _snapshot_is_stale_for_latest_run(
        *,
        snapshot_updated_at: datetime | None,
        latest_run: AgentRun | None,
    ) -> bool:
        if snapshot_updated_at is None or latest_run is None or latest_run.status is AgentRunStatus.RUNNING:
            return False
        latest_checkpoint = latest_run.completed_at or latest_run.started_at
        if latest_checkpoint is None:
            return False
        return snapshot_updated_at <= latest_checkpoint

    def _load_latest_event(self, agent_name: str) -> SystemEvent | None:
        return self.session.exec(
            select(SystemEvent)
            .where(SystemEvent.agent_name == agent_name)
            .order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc())
            .limit(1)
        ).first()

    def _load_progress_snapshot(self, agent_name: str) -> dict[str, object] | None:
        if self.runtime_dir is None:
            return None

        snapshot_path = self.runtime_dir / agent_name / "progress.json"
        if not snapshot_path.is_file():
            return None

        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _count_repositories(self, *conditions: object) -> int:
        statement = select(func.count()).select_from(RepositoryIntake)
        for condition in conditions:
            statement = statement.where(condition)
        return int(self.session.exec(statement).one() or 0)

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    @staticmethod
    def _to_optional_str(value: object) -> str | None:
        return value if isinstance(value, str) and value else None
