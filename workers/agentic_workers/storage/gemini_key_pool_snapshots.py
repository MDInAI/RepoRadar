from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from agentic_workers.storage.agent_progress_snapshots import _write_snapshot


def write_gemini_key_pool_snapshot(
    *,
    runtime_dir: Path | None,
    model_name: str | None,
    base_url: str | None,
    keys: list[dict[str, object]],
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / "gemini" / "key_pool.json"
    payload = {
        "provider": "gemini-compatible",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "base_url": base_url,
        "keys": keys,
    }
    _write_snapshot(snapshot_path, payload)
    return snapshot_path


def load_gemini_key_pool_snapshot(*, runtime_dir: Path | None) -> dict[str, object] | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / "gemini" / "key_pool.json"
    if not snapshot_path.is_file():
        return None

    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
