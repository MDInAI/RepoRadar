from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


def write_agent_progress_snapshot(
    *,
    runtime_dir: Path | None,
    agent_name: str,
    payload: dict[str, object],
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / agent_name / "progress.json"
    snapshot_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    _write_snapshot(snapshot_path, snapshot_payload)
    return snapshot_path


def clear_agent_progress_snapshot(
    *,
    runtime_dir: Path | None,
    agent_name: str,
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / agent_name / "progress.json"
    if not snapshot_path.exists():
        return None

    snapshot_path.unlink(missing_ok=True)
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
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise
