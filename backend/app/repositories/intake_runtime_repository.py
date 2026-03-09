from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    BackfillProgress,
    FirehoseProgress,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotMirrorState:
    generated_at: datetime | None = None
    issue_note: str | None = None


@dataclass(frozen=True, slots=True)
class IntakeStateCounts:
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0

    @property
    def total_items(self) -> int:
        return self.pending + self.in_progress + self.completed + self.failed


@dataclass(frozen=True, slots=True)
class FirehoseIntakeRuntimeRecord:
    counts: IntakeStateCounts
    active_mode: str | None
    next_page: int
    resume_required: bool | None
    new_anchor_date: date | None
    trending_anchor_date: date | None
    run_started_at: datetime | None
    last_checkpointed_at: datetime | None
    mirror_snapshot_generated_at: datetime | None
    snapshot_issue_note: str | None


@dataclass(frozen=True, slots=True)
class BackfillIntakeRuntimeRecord:
    counts: IntakeStateCounts
    window_start_date: date | None
    created_before_boundary: date | None
    created_before_cursor: datetime | None
    next_page: int
    exhausted: bool | None
    last_checkpointed_at: datetime | None
    mirror_snapshot_generated_at: datetime | None
    snapshot_issue_note: str | None


class IntakeRuntimeRepository:
    """Load intake runtime state from a single request-scoped SQLModel session.

    Instances are not thread-safe because they hold a mutable Session reference.
    Create a fresh repository per request or unit of work instead of sharing
    one across threads or concurrent tasks.
    """

    def __init__(
        self,
        session: Session,
        *,
        runtime_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.runtime_dir = runtime_dir

    def load_firehose_runtime(self) -> FirehoseIntakeRuntimeRecord:
        progress = self.session.get(FirehoseProgress, "github")
        snapshot_state = self._load_snapshot_state("firehose")
        return FirehoseIntakeRuntimeRecord(
            counts=self._load_counts(RepositoryDiscoverySource.FIREHOSE),
            active_mode=progress.active_mode.value if progress and progress.active_mode else None,
            next_page=progress.next_page if progress else 1,
            resume_required=progress.resume_required if progress else None,
            new_anchor_date=progress.new_anchor_date if progress else None,
            trending_anchor_date=progress.trending_anchor_date if progress else None,
            run_started_at=progress.run_started_at if progress else None,
            last_checkpointed_at=progress.last_checkpointed_at if progress else None,
            mirror_snapshot_generated_at=snapshot_state.generated_at,
            snapshot_issue_note=snapshot_state.issue_note,
        )

    def load_backfill_runtime(self) -> BackfillIntakeRuntimeRecord:
        progress = self.session.get(BackfillProgress, "github")
        snapshot_state = self._load_snapshot_state("backfill")
        return BackfillIntakeRuntimeRecord(
            counts=self._load_counts(RepositoryDiscoverySource.BACKFILL),
            window_start_date=progress.window_start_date if progress else None,
            created_before_boundary=progress.created_before_boundary if progress else None,
            created_before_cursor=progress.created_before_cursor if progress else None,
            next_page=progress.next_page if progress else 1,
            exhausted=progress.exhausted if progress else None,
            last_checkpointed_at=progress.last_checkpointed_at if progress else None,
            mirror_snapshot_generated_at=snapshot_state.generated_at,
            snapshot_issue_note=snapshot_state.issue_note,
        )

    def _load_counts(self, discovery_source: RepositoryDiscoverySource) -> IntakeStateCounts:
        rows = self.session.exec(
            select(
                RepositoryIntake.queue_status,
                func.count(RepositoryIntake.github_repository_id),
            )
            .where(RepositoryIntake.discovery_source == discovery_source)
            .group_by(RepositoryIntake.queue_status)
        ).all()

        counts_by_status = {status.value: 0 for status in RepositoryQueueStatus}
        for queue_status, count in rows:
            counts_by_status[queue_status.value] = int(count)

        return IntakeStateCounts(
            pending=counts_by_status[RepositoryQueueStatus.PENDING.value],
            in_progress=counts_by_status[RepositoryQueueStatus.IN_PROGRESS.value],
            completed=counts_by_status[RepositoryQueueStatus.COMPLETED.value],
            failed=counts_by_status[RepositoryQueueStatus.FAILED.value],
        )

    def _load_snapshot_state(self, intake_key: str) -> SnapshotMirrorState:
        if self.runtime_dir is None:
            return SnapshotMirrorState()

        snapshot_path = self.runtime_dir / intake_key / "progress.json"
        if not snapshot_path.is_file():
            return SnapshotMirrorState()

        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except OSError:
            logger.warning("Unable to read intake snapshot at %s.", snapshot_path)
            return SnapshotMirrorState(
                issue_note=(
                    f"The runtime/{intake_key}/progress.json mirror snapshot is currently unreadable."
                )
            )
        except json.JSONDecodeError:
            logger.warning("Unable to parse intake snapshot JSON at %s.", snapshot_path)
            return SnapshotMirrorState(
                issue_note=(
                    f"The runtime/{intake_key}/progress.json mirror snapshot is currently invalid."
                )
            )

        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, str):
            logger.warning(
                "Ignoring intake snapshot at %s because generated_at is missing or invalid.",
                snapshot_path,
            )
            return SnapshotMirrorState(
                issue_note=(
                    f"The runtime/{intake_key}/progress.json mirror snapshot is missing generated_at."
                )
            )

        try:
            return SnapshotMirrorState(generated_at=datetime.fromisoformat(generated_at))
        except ValueError:
            logger.warning(
                "Ignoring intake snapshot at %s because generated_at is not ISO-8601.",
                snapshot_path,
            )
            return SnapshotMirrorState(
                issue_note=(
                    f"The runtime/{intake_key}/progress.json mirror snapshot has an invalid timestamp."
                )
            )
