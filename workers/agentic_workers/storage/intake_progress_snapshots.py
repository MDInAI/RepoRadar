from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from agentic_workers.storage.backfill_progress import BackfillCheckpointState
from agentic_workers.storage.firehose_progress import FirehoseCheckpointState


def write_backfill_progress_snapshot(
    *,
    runtime_dir: Path | None,
    checkpoint: BackfillCheckpointState,
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / "backfill" / "progress.json"
    _write_snapshot(
        snapshot_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_provider": checkpoint.source_provider,
            "window_start_date": checkpoint.window_start_date.isoformat(),
            "window_end_date": (checkpoint.created_before_boundary - timedelta(days=1)).isoformat(),
            "created_before_boundary": checkpoint.created_before_boundary.isoformat(),
            "created_before_cursor": (
                checkpoint.created_before_cursor.isoformat()
                if checkpoint.created_before_cursor is not None
                else None
            ),
            "next_page": checkpoint.next_page,
            "pages_processed_in_run": checkpoint.pages_processed_in_run,
            "exhausted": checkpoint.exhausted,
            "resume_required": checkpoint.resume_required,
            "last_checkpointed_at": (
                checkpoint.last_checkpointed_at.isoformat()
                if checkpoint.last_checkpointed_at is not None
                else None
            ),
        },
    )
    return snapshot_path


def write_firehose_progress_snapshot(
    *,
    runtime_dir: Path | None,
    checkpoint: FirehoseCheckpointState,
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / "firehose" / "progress.json"
    _write_snapshot(
        snapshot_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_provider": checkpoint.source_provider,
            "active_mode": checkpoint.active_mode.value if checkpoint.active_mode is not None else None,
            "next_page": checkpoint.next_page,
            "pages_processed_in_run": checkpoint.pages_processed_in_run,
            "resume_required": checkpoint.resume_required,
            "run_started_at": (
                checkpoint.run_started_at.isoformat()
                if checkpoint.run_started_at is not None
                else None
            ),
            "last_checkpointed_at": (
                checkpoint.last_checkpointed_at.isoformat()
                if checkpoint.last_checkpointed_at is not None
                else None
            ),
            "anchors": {
                "new": checkpoint.new_anchor_date.isoformat()
                if checkpoint.new_anchor_date is not None
                else None,
                "trending": checkpoint.trending_anchor_date.isoformat()
                if checkpoint.trending_anchor_date is not None
                else None,
            },
        },
    )
    return snapshot_path


def _write_snapshot(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    except Exception:
        # Clean up temp file on failure
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise
