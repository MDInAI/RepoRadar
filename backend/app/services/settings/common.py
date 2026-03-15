from __future__ import annotations

import logging
import math
from typing import Any

from app.core.errors import AppError
from app.schemas.settings import (
    ConfigurationOwnership,
    ConfigurationValidationIssue,
    ConfigurationValidationResult,
)
from app.services.openclaw.transport import CONFIG_VALIDATION_STATUS_CODE

logger = logging.getLogger(__name__)

# Two Firehose discovery modes: NEW (recently created repos) and TRENDING (recently pushed repos).
_FIREHOSE_MODE_COUNT = 2

# Default pages-per-mode used when FIREHOSE_PAGES is not explicitly configured in the environment.
_DEFAULT_FIREHOSE_PAGES = 3


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_string(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return False


def _calculate_effective_intake_pacing(
    github_requests_per_minute: int,
    intake_pacing_seconds: int,
) -> int:
    request_budget_floor = math.ceil(60 / github_requests_per_minute)
    return max(intake_pacing_seconds, request_budget_floor)


def _calculate_effective_backfill_interval(
    configured_interval: int,
    github_requests_per_minute: int,
    intake_pacing_seconds: int,
    firehose_pages: int,
    backfill_pages: int,
) -> int:
    if configured_interval <= 0:
        raise ValueError("backfill_interval_seconds must be greater than zero")

    effective_pacing = _calculate_effective_intake_pacing(
        github_requests_per_minute,
        intake_pacing_seconds,
    )
    firehose_requests = _FIREHOSE_MODE_COUNT * firehose_pages
    min_cycle = (firehose_requests + backfill_pages) * effective_pacing
    return max(configured_interval, min_cycle)


def _calculate_effective_firehose_interval(
    configured_interval: int,
    github_requests_per_minute: int,
    intake_pacing_seconds: int,
    firehose_pages: int,
    backfill_pages: int,
) -> int:
    if configured_interval <= 0:
        raise ValueError("firehose_interval_seconds must be greater than zero")

    effective_pacing = _calculate_effective_intake_pacing(
        github_requests_per_minute,
        intake_pacing_seconds,
    )
    firehose_requests = _FIREHOSE_MODE_COUNT * firehose_pages
    min_cycle = (firehose_requests + backfill_pages) * effective_pacing
    return max(configured_interval, min_cycle)


def _raise_validation_error(
    issues: list[ConfigurationValidationIssue],
) -> None:
    logger.warning(
        "Configuration validation failed with %d error(s)",
        sum(1 for i in issues if i.severity == "error"),
    )
    validation = ConfigurationValidationResult(valid=False, issues=issues)
    raise AppError(
        message="Configuration validation failed.",
        code="settings_validation_failed",
        status_code=CONFIG_VALIDATION_STATUS_CODE,
        details={"validation": validation.model_dump()},
    )


def _ownership_entries() -> list[ConfigurationOwnership]:
    return [
        ConfigurationOwnership(
            key="openclaw.native-config",
            owner="openclaw",
            access="read-only-reference",
            source="~/.openclaw/openclaw.json",
            description=(
                "OpenClaw-native config owns shared control-plane conventions such as default models and channel definitions."
            ),
            surfaces=["backend services", "settings summary"],
            notes=["The browser never reads this file directly."],
        ),
        ConfigurationOwnership(
            key="gateway.transport",
            owner="gateway",
            access="read-only-reference",
            source="openclaw-config.gateway.*",
            description=(
                "Gateway transport details are sourced from OpenClaw-owned config and normalized by backend services."
            ),
            surfaces=["backend transport helpers", "settings summary", "gateway contract routes"],
            notes=["Gateway auth and connectivity details stay masked in app responses."],
        ),
        ConfigurationOwnership(
            key="workspace.context",
            owner="workspace",
            access="project-owned",
            source="OPENCLAW_WORKSPACE_DIR",
            description=(
                "Workspace context points the app and workers at checked-out local repositories and runtime inputs."
            ),
            surfaces=["workers", "backend settings summary"],
            notes=[
                "Workspace files remain separate from Gateway and OpenClaw control-plane ownership."
            ],
        ),
        ConfigurationOwnership(
            key="agentic-workflow.runtime",
            owner="agentic-workflow",
            access="project-owned",
            source="project env files",
            description=(
                "Agentic-Workflow owns runtime paths, persistence settings, provider credentials, and pacing thresholds."
            ),
            surfaces=["backend", "workers", "settings summary"],
            notes=[
                "Project-owned settings must never duplicate OpenClaw-native secrets or browser-exposed config."
            ],
        ),
    ]
