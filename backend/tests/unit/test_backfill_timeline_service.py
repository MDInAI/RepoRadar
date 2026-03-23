from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import json

import pytest
from sqlmodel import Session, select

from app.core.errors import AppError
from app.models import AgentPauseState, AgentRun, AgentRunStatus, BackfillProgress
from app.schemas.agent_timeline import BackfillTimelineUpdateRequest
from app.services.backfill_timeline_service import BackfillTimelineService


def test_get_timeline_returns_existing_checkpoint(session: Session, tmp_path: Path) -> None:
    session.add(
        BackfillProgress(
            source_provider="github",
            window_start_date=date(2025, 9, 15),
            created_before_boundary=date(2025, 10, 15),
            next_page=1,
            exhausted=False,
            resume_required=False,
            last_checkpointed_at=datetime(2026, 3, 15, 10, 45, tzinfo=timezone.utc),
        )
    )
    session.commit()

    service = BackfillTimelineService(session, runtime_dir=tmp_path)
    response = service.get_timeline()

    assert response.oldest_date_in_window == date(2025, 9, 15)
    assert response.newest_boundary_exclusive == date(2025, 10, 15)


def test_update_timeline_resets_cursor_and_marks_resume_required(session: Session, tmp_path: Path) -> None:
    session.add(
        BackfillProgress(
            source_provider="github",
            window_start_date=date(2025, 9, 15),
            created_before_boundary=date(2025, 10, 15),
            created_before_cursor=datetime(2025, 10, 1, 12, 0, tzinfo=timezone.utc),
            next_page=3,
            pages_processed_in_run=2,
            exhausted=False,
            resume_required=False,
            last_checkpointed_at=datetime(2026, 3, 15, 10, 45, tzinfo=timezone.utc),
        )
    )
    session.commit()

    service = BackfillTimelineService(session, runtime_dir=tmp_path)
    response = service.update_timeline(
        BackfillTimelineUpdateRequest(
            oldest_date_in_window=date(2025, 8, 1),
            newest_boundary_exclusive=date(2025, 9, 1),
        )
    )

    progress = session.get(BackfillProgress, "github")
    assert progress is not None
    assert progress.window_start_date == date(2025, 8, 1)
    assert progress.created_before_boundary == date(2025, 9, 1)
    assert progress.created_before_cursor is None
    assert progress.next_page == 1
    assert progress.resume_required is True
    assert response.message.startswith("Saved Backfill timeline and paused Backfill intentionally")

    pause_state = session.exec(
        select(AgentPauseState).where(AgentPauseState.agent_name == "backfill")
    ).first()
    assert pause_state is not None
    assert pause_state.is_paused is True
    assert pause_state.pause_reason is not None
    assert "timeline change" in pause_state.pause_reason

    snapshot = json.loads((tmp_path / "backfill" / "progress.json").read_text(encoding="utf-8"))
    assert snapshot["window_start_date"] == "2025-08-01"
    assert snapshot["created_before_boundary"] == "2025-09-01"


def test_update_timeline_stops_running_backfill_and_requires_manual_resume(
    session: Session,
    tmp_path: Path,
) -> None:
    session.add(
        BackfillProgress(
            source_provider="github",
            window_start_date=date(2025, 9, 15),
            created_before_boundary=date(2025, 10, 15),
            next_page=4,
            exhausted=False,
            resume_required=False,
            last_checkpointed_at=datetime(2026, 3, 15, 10, 45, tzinfo=timezone.utc),
        )
    )
    session.add(AgentRun(agent_name="backfill", status=AgentRunStatus.RUNNING))
    session.commit()

    service = BackfillTimelineService(session, runtime_dir=tmp_path)
    response = service.update_timeline(
        BackfillTimelineUpdateRequest(
            oldest_date_in_window=date(2026, 1, 10),
            newest_boundary_exclusive=date(2026, 1, 11),
        )
    )

    run = session.exec(select(AgentRun).where(AgentRun.agent_name == "backfill")).first()
    assert run is not None
    assert run.status is AgentRunStatus.SKIPPED
    assert run.completed_at is not None
    assert run.error_summary == "Stopped after the Backfill timeline changed."

    pause_state = session.exec(
        select(AgentPauseState).where(AgentPauseState.agent_name == "backfill")
    ).first()
    assert pause_state is not None
    assert pause_state.is_paused is True
    assert pause_state.resume_condition == (
        "Resume Backfill manually to start scanning from the newly saved historical window."
    )
    assert "paused Backfill intentionally" in response.message


def test_update_timeline_rejects_invalid_date_range(session: Session, tmp_path: Path) -> None:
    session.add(
        BackfillProgress(
            source_provider="github",
            window_start_date=date(2025, 9, 15),
            created_before_boundary=date(2025, 10, 15),
            next_page=1,
            exhausted=False,
            resume_required=False,
        )
    )
    session.commit()

    service = BackfillTimelineService(session, runtime_dir=tmp_path)
    with pytest.raises(AppError, match="earlier than the newest boundary"):
        service.update_timeline(
            BackfillTimelineUpdateRequest(
                oldest_date_in_window=date(2025, 10, 15),
                newest_boundary_exclusive=date(2025, 10, 15),
            )
        )
