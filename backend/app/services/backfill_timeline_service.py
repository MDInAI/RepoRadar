from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sqlmodel import Session

from app.core.errors import AppError
from app.models import AgentPauseState, AgentRun, AgentRunStatus, BackfillProgress
from app.schemas.agent_timeline import (
    BackfillTimelineResponse,
    BackfillTimelineUpdateRequest,
    BackfillTimelineUpdateResponse,
)
from sqlmodel import select


class BackfillTimelineService:
    def __init__(self, session: Session, *, runtime_dir: Path | None = None) -> None:
        self.session = session
        self.runtime_dir = runtime_dir

    def get_timeline(self) -> BackfillTimelineResponse:
        progress = self._require_progress()
        return self._build_response(progress)

    def update_timeline(
        self,
        request: BackfillTimelineUpdateRequest,
    ) -> BackfillTimelineUpdateResponse:
        if request.oldest_date_in_window >= request.newest_boundary_exclusive:
            raise AppError(
                message="The oldest date in the window must be earlier than the newest boundary.",
                code="backfill_timeline_invalid_range",
                status_code=400,
            )

        progress = self._require_progress()
        progress.window_start_date = request.oldest_date_in_window
        progress.created_before_boundary = request.newest_boundary_exclusive
        progress.created_before_cursor = None
        progress.next_page = 1
        progress.pages_processed_in_run = 0
        progress.exhausted = False
        progress.resume_required = True
        progress.last_checkpointed_at = datetime.now(timezone.utc)
        self.session.add(progress)

        pause_state = self.session.exec(
            select(AgentPauseState).where(AgentPauseState.agent_name == "backfill")
        ).first()
        if pause_state is None:
            pause_state = AgentPauseState(agent_name="backfill", is_paused=False)

        pause_state.is_paused = True
        pause_state.paused_at = datetime.now(timezone.utc)
        pause_state.pause_reason = (
            "Paused after a Backfill timeline change so the new historical window does not get "
            "overwritten by an older checkpoint."
        )
        pause_state.resume_condition = (
            "Resume Backfill manually to start scanning from the newly saved historical window."
        )
        pause_state.triggered_by_event_id = None
        pause_state.resumed_at = None
        pause_state.resumed_by = None
        self.session.add(pause_state)

        now = datetime.now(timezone.utc)
        running_runs = list(
            self.session.exec(
                select(AgentRun)
                .where(AgentRun.agent_name == "backfill")
                .where(AgentRun.status == AgentRunStatus.RUNNING)
            ).all()
        )
        for run in running_runs:
            run.status = AgentRunStatus.SKIPPED
            run.completed_at = now
            run.duration_seconds = max((now - run.started_at).total_seconds(), 0.0)
            run.error_summary = "Stopped after the Backfill timeline changed."
            run.error_context = (
                "An operator saved a new Backfill historical window, so the previous running "
                "checkpoint was stopped to prevent it from continuing to older dates."
            )
            self.session.add(run)

        self.session.commit()
        self.session.refresh(progress)
        self.session.refresh(pause_state)

        self._write_snapshot(progress)
        response = self._build_response(progress)
        return BackfillTimelineUpdateResponse(
            **response.model_dump(),
            message=(
                "Saved Backfill timeline and paused Backfill intentionally. Resume Backfill "
                "manually when you want it to restart from this new historical window."
            ),
        )

    def _require_progress(self) -> BackfillProgress:
        progress = self.session.get(BackfillProgress, "github")
        if progress is None:
            raise AppError(
                message="Backfill progress has not been initialized yet, so there is no timeline window to edit.",
                code="backfill_timeline_missing",
                status_code=404,
            )
        return progress

    def _build_response(self, progress: BackfillProgress) -> BackfillTimelineResponse:
        return BackfillTimelineResponse(
            oldest_date_in_window=progress.window_start_date,
            newest_boundary_exclusive=progress.created_before_boundary,
            current_cursor=progress.created_before_cursor,
            next_page=progress.next_page,
            exhausted=progress.exhausted,
            resume_required=progress.resume_required,
            last_checkpointed_at=progress.last_checkpointed_at,
            summary=(
                "Backfill scans repositories whose GitHub created date falls inside this current "
                "historical window. It starts from the newer boundary side and then moves the whole "
                "window backward over time."
            ),
            notes=[
                "Oldest date in window: inclusive lower bound for created_at.",
                "Newest boundary: exclusive upper bound for created_at.",
                "After saving, paging cursor resets so Backfill restarts this window from the top.",
                "Saving a new timeline pauses Backfill on purpose so older checkpoints cannot keep moving it backward.",
            ],
        )

    def _write_snapshot(self, progress: BackfillProgress) -> None:
        if self.runtime_dir is None:
            return

        snapshot_path = self.runtime_dir / "backfill" / "progress.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_provider": progress.source_provider,
            "window_start_date": progress.window_start_date.isoformat(),
            "window_end_date": (progress.created_before_boundary - timedelta(days=1)).isoformat(),
            "created_before_boundary": progress.created_before_boundary.isoformat(),
            "created_before_cursor": (
                progress.created_before_cursor.isoformat()
                if progress.created_before_cursor is not None
                else None
            ),
            "next_page": progress.next_page,
            "pages_processed_in_run": progress.pages_processed_in_run,
            "exhausted": progress.exhausted,
            "resume_required": progress.resume_required,
            "last_checkpointed_at": (
                progress.last_checkpointed_at.isoformat()
                if progress.last_checkpointed_at is not None
                else None
            ),
        }
        snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
