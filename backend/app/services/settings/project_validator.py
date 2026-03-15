from __future__ import annotations

import logging
import os

from app.core.config import Settings
from app.schemas.settings import (
    ConfigurationValidationIssue,
    MaskedSettingSummary,
)
from app.services.settings.common import (
    _DEFAULT_FIREHOSE_PAGES,
    _calculate_effective_firehose_interval,
    _calculate_effective_backfill_interval,
)

logger = logging.getLogger(__name__)


def _process_env_int(key: str, *, default: int) -> int:
    raw_value = os.getenv(key)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def validate_project_settings(
    app_settings: Settings,
) -> list[ConfigurationValidationIssue]:
    issues: list[ConfigurationValidationIssue] = []

    if not app_settings.DATABASE_URL.strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="DATABASE_URL",
                owner="agentic-workflow",
                code="project_database_url_missing",
                message="Project database URL is required.",
                source="project-env",
            )
        )

    runtime_dir = app_settings.AGENTIC_RUNTIME_DIR
    if not runtime_dir or not str(runtime_dir).strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="AGENTIC_RUNTIME_DIR",
                owner="agentic-workflow",
                code="runtime_dir_missing",
                message="Project runtime directory is required.",
                source="project-env",
            )
        )
    elif runtime_dir.exists() and not runtime_dir.is_dir():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="AGENTIC_RUNTIME_DIR",
                owner="agentic-workflow",
                code="runtime_dir_invalid",
                message="Project runtime directory must point to a directory path.",
                source="project-env",
            )
        )

    workspace_dir = app_settings.OPENCLAW_WORKSPACE_DIR
    if workspace_dir is None or not str(workspace_dir).strip():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_WORKSPACE_DIR",
                owner="workspace",
                code="workspace_dir_missing",
                message="Workspace path is required for worker-side local context.",
                source="project-env",
            )
        )
    elif not workspace_dir.is_dir():
        issues.append(
            ConfigurationValidationIssue(
                severity="error",
                field="OPENCLAW_WORKSPACE_DIR",
                owner="workspace",
                code="workspace_dir_invalid",
                message="Workspace path must point to an existing directory.",
                source="project-env",
            )
        )

    if issues:
        logger.info(
            "Project settings validation: %d error(s) found",
            sum(1 for i in issues if i.severity == "error"),
        )
    else:
        logger.info("Project settings validation passed")

    return issues


def project_setting_summaries(app_settings: Settings) -> list[MaskedSettingSummary]:
    runtime = app_settings.backend_runtime
    provider = app_settings.backend_provider
    reference = app_settings.openclaw_reference

    effective_backfill_interval = _calculate_effective_backfill_interval(
        provider.backfill_interval_seconds,
        provider.github_requests_per_minute,
        provider.intake_pacing_seconds,
        _process_env_int("FIREHOSE_PAGES", default=_DEFAULT_FIREHOSE_PAGES),
        provider.backfill_pages,
    )
    effective_firehose_interval = _calculate_effective_firehose_interval(
        provider.firehose_interval_seconds,
        provider.github_requests_per_minute,
        provider.intake_pacing_seconds,
        _process_env_int("FIREHOSE_PAGES", default=_DEFAULT_FIREHOSE_PAGES),
        provider.backfill_pages,
    )

    if effective_backfill_interval != provider.backfill_interval_seconds:
        logger.warning(
            "Backfill interval clamped: configured=%ds, effective=%ds",
            provider.backfill_interval_seconds,
            effective_backfill_interval,
        )
    if effective_firehose_interval != provider.firehose_interval_seconds:
        logger.warning(
            "Firehose interval clamped: configured=%ds, effective=%ds",
            provider.firehose_interval_seconds,
            effective_firehose_interval,
        )

    logger.debug(
        "Building project setting summaries: database_url configured=%s, runtime_dir=%s",
        bool(runtime.database_url),
        runtime.runtime_dir,
    )

    return [
        MaskedSettingSummary(
            key="DATABASE_URL",
            label="Backend database URL",
            owner="agentic-workflow",
            source="project-env",
            configured=bool(runtime.database_url),
            required=True,
            value=runtime.database_url,
            notes=["Project-owned runtime storage stays outside OpenClaw-native config."],
        ),
        MaskedSettingSummary(
            key="AGENTIC_RUNTIME_DIR",
            label="Project runtime directory",
            owner="agentic-workflow",
            source="project-env",
            configured=bool(runtime.runtime_dir and str(runtime.runtime_dir).strip()),
            required=True,
            value=str(runtime.runtime_dir) if runtime.runtime_dir else None,
            notes=["Agentic-Workflow owns local runtime paths and generated artifacts."],
        ),
        MaskedSettingSummary(
            key="OPENCLAW_WORKSPACE_DIR",
            label="Workspace root",
            owner="workspace",
            source="project-env",
            configured=reference.workspace_dir is not None,
            required=True,
            value=str(reference.workspace_dir) if reference.workspace_dir else None,
            notes=[
                "Workspace context remains separate from Gateway and OpenClaw control-plane state."
            ],
        ),
        MaskedSettingSummary(
            key="GITHUB_PROVIDER_TOKEN",
            label="GitHub provider token",
            owner="agentic-workflow",
            source="project-env",
            configured=provider.github_provider_token_configured,
            required=False,
            secret=True,
            value="configured" if provider.github_provider_token_configured else "missing",
            notes=["Provider credentials remain project-owned and are never returned raw."],
        ),
        MaskedSettingSummary(
            key="GITHUB_REQUESTS_PER_MINUTE",
            label="GitHub intake request budget",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.github_requests_per_minute),
            notes=["Project-specific pacing thresholds remain app-owned tuning knobs."],
        ),
        MaskedSettingSummary(
            key="INTAKE_PACING_SECONDS",
            label="Repository intake pacing interval",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.intake_pacing_seconds),
            notes=["Worker pacing stays project-owned rather than OpenClaw-native."],
        ),
        MaskedSettingSummary(
            key="FIREHOSE_INTERVAL_SECONDS",
            label="Firehose interval",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(effective_firehose_interval),
            notes=[
                "Firehose cadence remains project-owned worker configuration.",
                f"Configured: {provider.firehose_interval_seconds}s, Effective (clamped by budget): {effective_firehose_interval}s",
            ],
        ),
        MaskedSettingSummary(
            key="FIREHOSE_PER_PAGE",
            label="Firehose page size",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.firehose_per_page),
            notes=["Real-time GitHub search page size stays in project-owned settings."],
        ),
        MaskedSettingSummary(
            key="FIREHOSE_PAGES",
            label="Firehose pages per mode",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.firehose_pages),
            notes=["Firehose pacing stays bounded by an explicit per-mode page cap."],
        ),
        MaskedSettingSummary(
            key="BACKFILL_INTERVAL_SECONDS",
            label="Backfill interval",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(effective_backfill_interval),
            notes=[
                "Backfill cadence remains project-owned worker configuration.",
                f"Configured: {provider.backfill_interval_seconds}s, Effective (clamped by budget): {effective_backfill_interval}s",
            ],
        ),
        MaskedSettingSummary(
            key="BACKFILL_PER_PAGE",
            label="Backfill page size",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.backfill_per_page),
            notes=["Historical GitHub search page size stays in project-owned settings."],
        ),
        MaskedSettingSummary(
            key="BACKFILL_PAGES",
            label="Backfill pages per run",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.backfill_pages),
            notes=["Backfill pacing stays bounded by an explicit per-run page cap."],
        ),
        MaskedSettingSummary(
            key="BACKFILL_WINDOW_DAYS",
            label="Backfill window size",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=str(provider.backfill_window_days),
            notes=["Historical search windows remain explicit and deterministic."],
        ),
        MaskedSettingSummary(
            key="BACKFILL_MIN_CREATED_DATE",
            label="Backfill oldest created date",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=True,
            value=provider.backfill_min_created_date.isoformat(),
            notes=["Historical backfill stays bounded by a project-owned oldest-date cutoff."],
        ),
        MaskedSettingSummary(
            key="BOUNCER_INCLUDE_RULES",
            label="Bouncer include rules",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=False,
            value=", ".join(provider.bouncer_include_rules) if provider.bouncer_include_rules else "none",
            notes=["Rule-based triage include rules remain explicit project-owned tuning."],
        ),
        MaskedSettingSummary(
            key="BOUNCER_EXCLUDE_RULES",
            label="Bouncer exclude rules",
            owner="agentic-workflow",
            source="project-env",
            configured=True,
            required=False,
            value=", ".join(provider.bouncer_exclude_rules) if provider.bouncer_exclude_rules else "none",
            notes=["Rule-based triage exclude rules remain explicit project-owned tuning."],
        ),
        MaskedSettingSummary(
            key="OPENCLAW_CONFIG_PATH",
            label="OpenClaw config path reference",
            owner="openclaw",
            source="project-env",
            configured=True,
            required=True,
            value=str(reference.config_path),
            notes=["The backend reads OpenClaw-owned config through this typed reference only."],
        ),
    ]
