from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.config import Settings
from app.schemas.settings import (
    ConfigurationValidationIssue,
    MaskedSettingSummary,
)
from app.services.settings.common import (
    _calculate_effective_backfill_interval,
    _calculate_effective_firehose_interval,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerSettingsProjection:
    database_url: str
    runtime_dir: Path
    workspace_dir: Path | None
    github_provider_token_configured: bool
    github_requests_per_minute: int
    intake_pacing_seconds: int
    firehose_interval_seconds: int
    firehose_per_page: int
    firehose_pages: int
    backfill_interval_seconds: int
    backfill_per_page: int
    backfill_pages: int
    backfill_window_days: int
    backfill_min_created_date: date
    bouncer_include_rules: tuple[str, ...]
    bouncer_exclude_rules: tuple[str, ...]
    source: str
    overrides_loaded: bool


def _parse_env_file(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    loaded = dotenv_values(path)
    return {k: v.strip() for k, v in loaded.items() if v is not None}


def _env_override(
    overrides: dict[str, str],
    key: str,
    fallback: str,
    *,
    applied_override_keys: set[str],
) -> str:
    if key in overrides and key not in os.environ:
        logger.debug("Worker override applied: %s", key)
        applied_override_keys.add(key)
        return overrides[key].strip()
    return fallback.strip()


def _optional_string_override(
    overrides: dict[str, str],
    key: str,
    fallback: str | None,
    *,
    applied_override_keys: set[str],
) -> str | None:
    if key in overrides and key not in os.environ:
        logger.debug("Worker override applied: %s", key)
        applied_override_keys.add(key)
        candidate = overrides[key]
    else:
        candidate = fallback or ""
    candidate = candidate.strip()
    return candidate or None


def _path_override(
    overrides: dict[str, str],
    key: str,
    fallback: Path | None,
    *,
    applied_override_keys: set[str],
) -> Path | None:
    if key not in overrides or key in os.environ:
        return fallback

    logger.debug("Worker override applied: %s", key)
    applied_override_keys.add(key)
    candidate = overrides[key].strip()
    if not candidate:
        return None
    return Path(candidate).expanduser()


def _optional_path_override(
    overrides: dict[str, str],
    key: str,
    fallback: Path | None,
    *,
    applied_override_keys: set[str],
) -> Path | None:
    if key not in overrides or key in os.environ:
        return fallback
    logger.debug("Worker override applied: %s", key)
    applied_override_keys.add(key)
    candidate = overrides[key]
    candidate = candidate.strip()
    if not candidate:
        return None
    return Path(candidate).expanduser()


def _int_override(
    overrides: dict[str, str],
    key: str,
    fallback: int,
    *,
    issues: list[ConfigurationValidationIssue],
    applied_override_keys: set[str],
) -> int:
    raw_value = overrides.get(key)
    if raw_value is None or key in os.environ:
        return fallback

    try:
        parsed = int(raw_value.strip())
    except ValueError:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field=f"workers.{key}",
                owner="agentic-workflow",
                code="worker_setting_invalid_integer",
                message=f"{key} must be a positive integer.",
                source="workers-env",
            )
        )
        return fallback

    if parsed <= 0:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field=f"workers.{key}",
                owner="agentic-workflow",
                code="worker_setting_invalid_integer",
                message=f"{key} must be a positive integer.",
                source="workers-env",
            )
        )
        return fallback

    logger.debug("Worker override applied: %s=%d", key, parsed)
    applied_override_keys.add(key)
    return parsed


def _date_override(
    overrides: dict[str, str],
    key: str,
    fallback: date,
    *,
    issues: list[ConfigurationValidationIssue],
    applied_override_keys: set[str],
) -> date:
    raw_value = overrides.get(key)
    if raw_value is None or key in os.environ:
        return fallback

    candidate = raw_value.strip()
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field=f"workers.{key}",
                owner="agentic-workflow",
                code="worker_setting_invalid_date",
                message=f"{key} must be an ISO date (YYYY-MM-DD).",
                source="workers-env",
            )
        )
        return fallback

    logger.debug("Worker override applied: %s=%s", key, parsed.isoformat())
    applied_override_keys.add(key)
    return parsed


def _tuple_override(
    overrides: dict[str, str],
    key: str,
    fallback: tuple[str, ...],
    *,
    applied_override_keys: set[str],
) -> tuple[str, ...]:
    raw_value = overrides.get(key)
    if raw_value is None or key in os.environ:
        return fallback

    candidate = raw_value.strip()
    if not candidate:
        logger.debug("Worker override applied: %s=<empty>", key)
        applied_override_keys.add(key)
        return ()

    if candidate.startswith("["):
        try:
            parsed = json.loads(candidate)
            normalized = tuple(str(part).strip() for part in parsed if str(part).strip())
            logger.debug("Worker override applied: %s=%s", key, normalized)
            applied_override_keys.add(key)
            return normalized
        except (json.JSONDecodeError, ValueError):
            pass

    normalized = tuple(part.strip() for part in candidate.split(",") if part.strip())
    logger.debug("Worker override applied: %s=%s", key, normalized)
    applied_override_keys.add(key)
    return normalized


def _process_env_int(key: str, *, default: int) -> int:
    import os as _os

    raw_value = _os.getenv(key)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _validate_worker_settings(
    worker: WorkerSettingsProjection,
) -> list[ConfigurationValidationIssue]:
    issues: list[ConfigurationValidationIssue] = []

    if not worker.database_url.strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="workers.DATABASE_URL",
                owner="agentic-workflow",
                code="worker_database_url_missing",
                message="Worker database URL is required.",
                source=worker.source,
            )
        )

    if not worker.runtime_dir or not str(worker.runtime_dir).strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="workers.AGENTIC_RUNTIME_DIR",
                owner="agentic-workflow",
                code="worker_runtime_dir_missing",
                message="Worker runtime directory is required.",
                source=worker.source,
            )
        )
    elif worker.runtime_dir.exists() and not worker.runtime_dir.is_dir():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="workers.AGENTIC_RUNTIME_DIR",
                owner="agentic-workflow",
                code="worker_runtime_dir_invalid",
                message="Worker runtime directory must point to a directory path.",
                source=worker.source,
            )
        )

    if worker.workspace_dir is None or not str(worker.workspace_dir).strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="workers.OPENCLAW_WORKSPACE_DIR",
                owner="workspace",
                code="worker_workspace_dir_missing",
                message="Worker workspace path is required for worker-side local context.",
                source=worker.source,
            )
        )
    elif not worker.workspace_dir.is_dir():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="workers.OPENCLAW_WORKSPACE_DIR",
                owner="workspace",
                code="worker_workspace_dir_invalid",
                message="Worker workspace path must point to an existing directory.",
                source=worker.source,
            )
        )

    return issues


def _detect_worker_drift(
    worker: WorkerSettingsProjection,
    app_settings: Settings,
) -> list[ConfigurationValidationIssue]:
    if not worker.overrides_loaded:
        return []

    issues: list[ConfigurationValidationIssue] = []
    comparisons = [
        (
            "workers.DATABASE_URL",
            "agentic-workflow",
            worker.database_url,
            app_settings.DATABASE_URL,
            "worker_database_url_differs",
            "Worker database URL differs from the backend process view.",
        ),
        (
            "workers.AGENTIC_RUNTIME_DIR",
            "agentic-workflow",
            str(worker.runtime_dir) if worker.runtime_dir else "",
            str(app_settings.AGENTIC_RUNTIME_DIR) if app_settings.AGENTIC_RUNTIME_DIR else "",
            "worker_runtime_dir_differs",
            "Worker runtime directory differs from the backend process view.",
        ),
        (
            "workers.OPENCLAW_WORKSPACE_DIR",
            "workspace",
            str(worker.workspace_dir) if worker.workspace_dir else "",
            str(app_settings.OPENCLAW_WORKSPACE_DIR) if app_settings.OPENCLAW_WORKSPACE_DIR else "",
            "worker_workspace_dir_differs",
            "Worker workspace directory differs from the backend process view.",
        ),
        (
            "workers.GITHUB_PROVIDER_TOKEN",
            "agentic-workflow",
            str(worker.github_provider_token_configured).lower(),
            str(app_settings.backend_provider.github_provider_token_configured).lower(),
            "worker_github_provider_token_differs",
            "Worker GitHub provider token configured-state differs from the backend process view.",
        ),
        (
            "workers.GITHUB_REQUESTS_PER_MINUTE",
            "agentic-workflow",
            str(worker.github_requests_per_minute),
            str(app_settings.GITHUB_REQUESTS_PER_MINUTE),
            "worker_github_requests_per_minute_differs",
            "Worker GitHub request budget differs from the backend process view.",
        ),
        (
            "workers.INTAKE_PACING_SECONDS",
            "agentic-workflow",
            str(worker.intake_pacing_seconds),
            str(app_settings.INTAKE_PACING_SECONDS),
            "worker_intake_pacing_seconds_differs",
            "Worker intake pacing interval differs from the backend process view.",
        ),
        (
            "workers.FIREHOSE_INTERVAL_SECONDS",
            "agentic-workflow",
            str(worker.firehose_interval_seconds),
            str(app_settings.FIREHOSE_INTERVAL_SECONDS),
            "worker_firehose_interval_seconds_differs",
            "Worker firehose interval differs from the backend process view.",
        ),
        (
            "workers.FIREHOSE_PER_PAGE",
            "agentic-workflow",
            str(worker.firehose_per_page),
            str(app_settings.FIREHOSE_PER_PAGE),
            "worker_firehose_per_page_differs",
            "Worker firehose page size differs from the backend process view.",
        ),
        (
            "workers.FIREHOSE_PAGES",
            "agentic-workflow",
            str(worker.firehose_pages),
            str(app_settings.FIREHOSE_PAGES),
            "worker_firehose_pages_differs",
            "Worker firehose pages-per-mode differs from the backend process view.",
        ),
        (
            "workers.BACKFILL_INTERVAL_SECONDS",
            "agentic-workflow",
            str(worker.backfill_interval_seconds),
            str(app_settings.BACKFILL_INTERVAL_SECONDS),
            "worker_backfill_interval_seconds_differs",
            "Worker backfill interval differs from the backend process view.",
        ),
        (
            "workers.BACKFILL_PER_PAGE",
            "agentic-workflow",
            str(worker.backfill_per_page),
            str(app_settings.BACKFILL_PER_PAGE),
            "worker_backfill_per_page_differs",
            "Worker backfill page size differs from the backend process view.",
        ),
        (
            "workers.BACKFILL_PAGES",
            "agentic-workflow",
            str(worker.backfill_pages),
            str(app_settings.BACKFILL_PAGES),
            "worker_backfill_pages_differs",
            "Worker backfill pages-per-run differs from the backend process view.",
        ),
        (
            "workers.BACKFILL_WINDOW_DAYS",
            "agentic-workflow",
            str(worker.backfill_window_days),
            str(app_settings.BACKFILL_WINDOW_DAYS),
            "worker_backfill_window_days_differs",
            "Worker backfill window size differs from the backend process view.",
        ),
        (
            "workers.BACKFILL_MIN_CREATED_DATE",
            "agentic-workflow",
            worker.backfill_min_created_date.isoformat(),
            app_settings.BACKFILL_MIN_CREATED_DATE.isoformat(),
            "worker_backfill_min_created_date_differs",
            "Worker backfill oldest created-date cutoff differs from the backend process view.",
        ),
    ]

    for field, owner, worker_value, backend_value, code, message in comparisons:
        if worker_value != backend_value:
            logger.warning(
                "Worker drift detected: %s (worker=%r, backend=%r)",
                field,
                worker_value,
                backend_value,
            )
            issues.append(
                ConfigurationValidationIssue(
                    severity="warning",
                    field=field,
                    owner=owner,
                    code=code,
                    message=message,
                    source=worker.source,
                )
            )

    return issues


def build_worker_projection(
    app_settings: Settings,
    project_root: Path,
) -> tuple[WorkerSettingsProjection, list[ConfigurationValidationIssue]]:
    issues: list[ConfigurationValidationIssue] = []
    worker_env_path = project_root / "workers" / ".env"
    overrides = _parse_env_file(worker_env_path) if worker_env_path.is_file() else {}
    applied_override_keys: set[str] = set()

    if overrides:
        logger.debug("Worker .env file found at %s", worker_env_path)

    database_url = _env_override(
        overrides,
        "DATABASE_URL",
        app_settings.DATABASE_URL,
        applied_override_keys=applied_override_keys,
    )
    runtime_dir = _path_override(
        overrides,
        "AGENTIC_RUNTIME_DIR",
        app_settings.AGENTIC_RUNTIME_DIR,
        applied_override_keys=applied_override_keys,
    )
    workspace_dir = _optional_path_override(
        overrides,
        "OPENCLAW_WORKSPACE_DIR",
        app_settings.OPENCLAW_WORKSPACE_DIR,
        applied_override_keys=applied_override_keys,
    )
    github_token = _optional_string_override(
        overrides,
        "GITHUB_PROVIDER_TOKEN",
        app_settings.github_provider_token_value,
        applied_override_keys=applied_override_keys,
    )
    requests_per_minute = _int_override(
        overrides,
        "GITHUB_REQUESTS_PER_MINUTE",
        app_settings.GITHUB_REQUESTS_PER_MINUTE,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    intake_pacing_seconds = _int_override(
        overrides,
        "INTAKE_PACING_SECONDS",
        app_settings.INTAKE_PACING_SECONDS,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    firehose_interval_seconds = _int_override(
        overrides,
        "FIREHOSE_INTERVAL_SECONDS",
        app_settings.FIREHOSE_INTERVAL_SECONDS,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    firehose_per_page = _int_override(
        overrides,
        "FIREHOSE_PER_PAGE",
        app_settings.FIREHOSE_PER_PAGE,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    firehose_pages = _int_override(
        overrides,
        "FIREHOSE_PAGES",
        _process_env_int("FIREHOSE_PAGES", default=3),
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    backfill_interval_seconds = _int_override(
        overrides,
        "BACKFILL_INTERVAL_SECONDS",
        app_settings.BACKFILL_INTERVAL_SECONDS,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    backfill_per_page = _int_override(
        overrides,
        "BACKFILL_PER_PAGE",
        app_settings.BACKFILL_PER_PAGE,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    backfill_pages = _int_override(
        overrides,
        "BACKFILL_PAGES",
        app_settings.BACKFILL_PAGES,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    backfill_window_days = _int_override(
        overrides,
        "BACKFILL_WINDOW_DAYS",
        app_settings.BACKFILL_WINDOW_DAYS,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    backfill_min_created_date = _date_override(
        overrides,
        "BACKFILL_MIN_CREATED_DATE",
        app_settings.BACKFILL_MIN_CREATED_DATE,
        issues=issues,
        applied_override_keys=applied_override_keys,
    )
    bouncer_include_rules = _tuple_override(
        overrides,
        "BOUNCER_INCLUDE_RULES",
        app_settings.BOUNCER_INCLUDE_RULES,
        applied_override_keys=applied_override_keys,
    )
    bouncer_exclude_rules = _tuple_override(
        overrides,
        "BOUNCER_EXCLUDE_RULES",
        app_settings.BOUNCER_EXCLUDE_RULES,
        applied_override_keys=applied_override_keys,
    )
    source = "workers-env" if applied_override_keys else "shared-project-env"

    projection = WorkerSettingsProjection(
        database_url=database_url,
        runtime_dir=runtime_dir,  # type: ignore[arg-type]
        workspace_dir=workspace_dir,
        github_provider_token_configured=bool(github_token),
        github_requests_per_minute=requests_per_minute,
        intake_pacing_seconds=intake_pacing_seconds,
        firehose_interval_seconds=firehose_interval_seconds,
        firehose_per_page=firehose_per_page,
        firehose_pages=firehose_pages,
        backfill_interval_seconds=backfill_interval_seconds,
        backfill_per_page=backfill_per_page,
        backfill_pages=backfill_pages,
        backfill_window_days=backfill_window_days,
        backfill_min_created_date=backfill_min_created_date,
        bouncer_include_rules=bouncer_include_rules,
        bouncer_exclude_rules=bouncer_exclude_rules,
        source=source,
        overrides_loaded=bool(applied_override_keys),
    )

    logger.info(
        "Worker projection built: source=%s, overrides_loaded=%s",
        source,
        projection.overrides_loaded,
    )

    issues.extend(_validate_worker_settings(projection))
    issues.extend(_detect_worker_drift(projection, app_settings))

    return projection, issues


def worker_setting_summaries(
    worker: WorkerSettingsProjection,
) -> list[MaskedSettingSummary]:
    source_notes = (
        "Worker-specific overrides are loaded from workers/.env."
        if worker.overrides_loaded
        else "Workers inherit the shared project env when launched via scripts/dev.sh."
    )
    workspace_value = str(worker.workspace_dir) if worker.workspace_dir else None

    worker_effective_firehose_interval = _calculate_effective_firehose_interval(
        worker.firehose_interval_seconds,
        worker.github_requests_per_minute,
        worker.intake_pacing_seconds,
        worker.firehose_pages,
        worker.backfill_pages,
    )
    worker_effective_backfill_interval = _calculate_effective_backfill_interval(
        worker.backfill_interval_seconds,
        worker.github_requests_per_minute,
        worker.intake_pacing_seconds,
        worker.firehose_pages,
        worker.backfill_pages,
    )

    if worker_effective_firehose_interval != worker.firehose_interval_seconds:
        logger.warning(
            "Worker firehose interval clamped: configured=%ds, effective=%ds",
            worker.firehose_interval_seconds,
            worker_effective_firehose_interval,
        )
    if worker_effective_backfill_interval != worker.backfill_interval_seconds:
        logger.warning(
            "Worker backfill interval clamped: configured=%ds, effective=%ds",
            worker.backfill_interval_seconds,
            worker_effective_backfill_interval,
        )

    return [
        MaskedSettingSummary(
            key="workers.DATABASE_URL",
            label="Worker database URL",
            owner="agentic-workflow",
            source=worker.source,
            configured=bool(worker.database_url),
            required=True,
            value=worker.database_url,
            notes=[
                source_notes,
                "Worker storage config is validated separately from backend settings.",
            ],
        ),
        MaskedSettingSummary(
            key="workers.AGENTIC_RUNTIME_DIR",
            label="Worker runtime directory",
            owner="agentic-workflow",
            source=worker.source,
            configured=bool(worker.runtime_dir and str(worker.runtime_dir).strip()),
            required=True,
            value=str(worker.runtime_dir) if worker.runtime_dir else None,
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.OPENCLAW_WORKSPACE_DIR",
            label="Worker workspace root",
            owner="workspace",
            source=worker.source,
            configured=worker.workspace_dir is not None,
            required=True,
            value=workspace_value,
            notes=[
                source_notes,
                "Worker workspace drift is surfaced so readiness does not only reflect backend config.",
            ],
        ),
        MaskedSettingSummary(
            key="workers.GITHUB_PROVIDER_TOKEN",
            label="Worker GitHub provider token",
            owner="agentic-workflow",
            source=worker.source,
            configured=worker.github_provider_token_configured,
            required=False,
            secret=True,
            value="configured" if worker.github_provider_token_configured else "missing",
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.GITHUB_REQUESTS_PER_MINUTE",
            label="Worker GitHub intake request budget",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.github_requests_per_minute),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.INTAKE_PACING_SECONDS",
            label="Worker intake pacing interval",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.intake_pacing_seconds),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.FIREHOSE_INTERVAL_SECONDS",
            label="Worker firehose interval",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker_effective_firehose_interval),
            notes=[
                source_notes,
                f"Configured: {worker.firehose_interval_seconds}s, Effective (clamped by budget): {worker_effective_firehose_interval}s",
            ],
        ),
        MaskedSettingSummary(
            key="workers.FIREHOSE_PER_PAGE",
            label="Worker firehose page size",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.firehose_per_page),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.FIREHOSE_PAGES",
            label="Worker firehose pages per mode",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.firehose_pages),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BACKFILL_INTERVAL_SECONDS",
            label="Worker backfill interval",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker_effective_backfill_interval),
            notes=[
                source_notes,
                f"Configured: {worker.backfill_interval_seconds}s, Effective (clamped by budget): {worker_effective_backfill_interval}s",
            ],
        ),
        MaskedSettingSummary(
            key="workers.BACKFILL_PER_PAGE",
            label="Worker backfill page size",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.backfill_per_page),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BACKFILL_PAGES",
            label="Worker backfill pages per run",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.backfill_pages),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BACKFILL_WINDOW_DAYS",
            label="Worker backfill window size",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=str(worker.backfill_window_days),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BACKFILL_MIN_CREATED_DATE",
            label="Worker backfill oldest created date",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=True,
            value=worker.backfill_min_created_date.isoformat(),
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BOUNCER_INCLUDE_RULES",
            label="Worker bouncer include rules",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=False,
            value=", ".join(worker.bouncer_include_rules) if worker.bouncer_include_rules else "none",
            notes=[source_notes],
        ),
        MaskedSettingSummary(
            key="workers.BOUNCER_EXCLUDE_RULES",
            label="Worker bouncer exclude rules",
            owner="agentic-workflow",
            source=worker.source,
            configured=True,
            required=False,
            value=", ".join(worker.bouncer_exclude_rules) if worker.bouncer_exclude_rules else "none",
            notes=[source_notes],
        ),
    ]
