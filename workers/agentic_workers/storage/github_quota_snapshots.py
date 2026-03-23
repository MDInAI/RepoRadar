from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from agentic_workers.storage.agent_progress_snapshots import _write_snapshot


def initialize_github_quota_snapshot(
    *,
    runtime_dir: Path | None,
    token_labels: tuple[str, ...] | list[str],
) -> Path | None:
    if runtime_dir is None:
        return None

    labels = [label.strip() for label in token_labels if isinstance(label, str) and label.strip()]
    snapshot_path = runtime_dir / "github" / "quota.json"
    existing_payload = _load_existing_payload(snapshot_path)
    existing_tokens = existing_payload.get("tokens")
    token_entries = existing_tokens if isinstance(existing_tokens, list) else []
    normalized_tokens = [entry for entry in token_entries if isinstance(entry, dict)]
    by_label = {
        str(entry.get("label")): dict(entry)
        for entry in normalized_tokens
        if isinstance(entry.get("label"), str) and str(entry.get("label")).strip()
    }

    captured_at = datetime.now(timezone.utc).isoformat()
    for label in labels:
        by_label.setdefault(
            label,
            {
                "label": label,
                "captured_at": captured_at,
                "last_response_status": None,
                "request_url": None,
                "resource": None,
                "limit": None,
                "remaining": None,
                "used": None,
                "reset_at": None,
                "retry_after_seconds": None,
                "exhausted": None,
                "last_used_at": None,
                "cooldown_until": None,
                "next_available_at": None,
                "in_flight": 0,
                "resource_budgets": [],
            },
        )

    payload = {
        **existing_payload,
        "provider": "github",
        "scheduler": existing_payload.get("scheduler")
        if isinstance(existing_payload.get("scheduler"), dict)
        else {},
        "tokens": [by_label[label] for label in sorted(by_label)],
    }
    _write_snapshot(snapshot_path, payload)
    return snapshot_path


def write_github_quota_snapshot(
    *,
    runtime_dir: Path | None,
    status_code: int | None,
    headers: object,
    token_label: str | None = None,
    token_labels: tuple[str, ...] | list[str] = (),
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
    merged_payload = _merge_snapshot_payload(
        snapshot_path=snapshot_path,
        observation=snapshot_payload,
        token_label=token_label,
        token_labels=token_labels,
    )
    _write_snapshot(snapshot_path, merged_payload)
    return snapshot_path


def _merge_snapshot_payload(
    *,
    snapshot_path: Path,
    observation: dict[str, object],
    token_label: str | None,
    token_labels: tuple[str, ...] | list[str],
) -> dict[str, object]:
    existing_payload = _load_existing_payload(snapshot_path)
    merged = {
        **existing_payload,
        **observation,
    }

    existing_tokens = existing_payload.get("tokens")
    token_entries = existing_tokens if isinstance(existing_tokens, list) else []
    normalized_tokens = [entry for entry in token_entries if isinstance(entry, dict)]
    by_label = {
        str(entry.get("label")): dict(entry)
        for entry in normalized_tokens
        if isinstance(entry.get("label"), str) and str(entry.get("label")).strip()
    }

    all_labels = [
        label.strip()
        for label in token_labels
        if isinstance(label, str) and label.strip()
    ]
    if token_label and token_label not in all_labels:
        all_labels.append(token_label)

    if token_label:
        previous = by_label.get(token_label, {})
        resource_budgets = previous.get("resource_budgets")
        budget_entries = resource_budgets if isinstance(resource_budgets, list) else []
        normalized_budgets = [entry for entry in budget_entries if isinstance(entry, dict)]
        resource_name = observation.get("resource")
        updated_budgets = []
        matched_resource = False
        for entry in normalized_budgets:
            if isinstance(resource_name, str) and entry.get("resource") == resource_name:
                updated_budgets.append(
                    {
                        "resource": resource_name,
                        "captured_at": observation.get("captured_at"),
                        "limit": observation.get("limit"),
                        "remaining": observation.get("remaining"),
                        "used": observation.get("used"),
                        "reset_at": observation.get("reset_at"),
                        "retry_after_seconds": observation.get("retry_after_seconds"),
                        "exhausted": observation.get("exhausted"),
                    }
                )
                matched_resource = True
            else:
                updated_budgets.append(entry)
        if isinstance(resource_name, str) and not matched_resource:
            updated_budgets.append(
                {
                    "resource": resource_name,
                    "captured_at": observation.get("captured_at"),
                    "limit": observation.get("limit"),
                    "remaining": observation.get("remaining"),
                    "used": observation.get("used"),
                    "reset_at": observation.get("reset_at"),
                    "retry_after_seconds": observation.get("retry_after_seconds"),
                    "exhausted": observation.get("exhausted"),
                }
            )

        by_label[token_label] = {
            **previous,
            **observation,
            "label": token_label,
            "resource_budgets": sorted(
                updated_budgets,
                key=lambda entry: str(entry.get("resource") or ""),
            ),
        }

    captured_at = str(observation.get("captured_at") or datetime.now(timezone.utc).isoformat())
    for label in all_labels:
        by_label.setdefault(
            label,
            {
                "label": label,
                "captured_at": captured_at,
                "last_response_status": None,
                "request_url": None,
                "resource": None,
                "limit": None,
                "remaining": None,
                "used": None,
                "reset_at": None,
                "retry_after_seconds": None,
                "exhausted": None,
                "resource_budgets": [],
            },
        )

    merged["tokens"] = [by_label[label] for label in sorted(by_label)]
    return merged


def write_github_scheduler_snapshot(
    *,
    runtime_dir: Path | None,
    scheduler: dict[str, object],
    tokens: list[dict[str, object]],
) -> Path | None:
    if runtime_dir is None:
        return None

    snapshot_path = runtime_dir / "github" / "quota.json"
    existing_payload = _load_existing_payload(snapshot_path)
    existing_tokens = existing_payload.get("tokens")
    token_entries = existing_tokens if isinstance(existing_tokens, list) else []
    by_label = {
        str(entry.get("label")): dict(entry)
        for entry in token_entries
        if isinstance(entry, dict) and isinstance(entry.get("label"), str)
    }

    for token in tokens:
        label = token.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        previous = by_label.get(label, {})
        by_label[label] = {
            **previous,
            **token,
        }

    payload = {
        **existing_payload,
        "provider": "github",
        "scheduler": scheduler,
        "tokens": [by_label[label] for label in sorted(by_label)],
    }
    _write_snapshot(snapshot_path, payload)
    return snapshot_path


def _load_existing_payload(snapshot_path: Path) -> dict[str, object]:
    if not snapshot_path.is_file():
        return {}
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
