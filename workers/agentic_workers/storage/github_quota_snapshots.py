from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentic_workers.storage.agent_progress_snapshots import _write_snapshot


def write_github_quota_snapshot(
    *,
    runtime_dir: Path | None,
    status_code: int | None,
    headers: object,
    request_url: str | None = None,
) -> Path | None:
    if runtime_dir is None or headers is None:
        return None

    get = getattr(headers, "get", None)
    if not callable(get):
        return None

    limit = _parse_optional_int(get("X-RateLimit-Limit"))
    remaining = _parse_optional_int(get("X-RateLimit-Remaining"))
    used = _parse_optional_int(get("X-RateLimit-Used"))
    reset_unix = _parse_optional_int(get("X-RateLimit-Reset"))
    resource = _parse_optional_str(get("X-RateLimit-Resource"))

    if limit is None and remaining is None and used is None and reset_unix is None and resource is None:
        return None

    reset_at = None
    retry_after_seconds = None
    if reset_unix is not None:
        reset_at = datetime.fromtimestamp(reset_unix, tz=timezone.utc).isoformat()
        retry_after_seconds = max(0, reset_unix - int(datetime.now(timezone.utc).timestamp()))

    exhausted = None
    if remaining is not None:
        exhausted = remaining <= 0

    snapshot_payload = {
        "provider": "github",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "last_response_status": status_code,
        "request_url": request_url,
        "resource": resource,
        "limit": limit,
        "remaining": remaining,
        "used": used,
        "reset_at": reset_at,
        "retry_after_seconds": retry_after_seconds,
        "exhausted": exhausted,
    }
    snapshot_path = runtime_dir / "github" / "quota.json"
    _write_snapshot(snapshot_path, snapshot_payload)
    return snapshot_path


def _parse_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None
