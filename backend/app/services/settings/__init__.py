"""Settings service package.

SettingsService is the sole public entry point.
Sub-modules contain domain-focused logic extracted for maintainability.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import Settings, settings
from app.schemas.settings import (
    ConfigurationValidationResult,
    SettingsSummaryResponse,
)
from app.services.settings.common import (
    _calculate_effective_backfill_interval,
    _ownership_entries,
    _raise_validation_error,
)
from app.services.settings.openclaw_validator import (
    build_openclaw_setting_summaries,
    load_openclaw_payload,
    resolve_openclaw_gateway_target,
)
from app.services.settings.project_validator import (
    project_setting_summaries,
    validate_project_settings,
)
from app.services.settings.worker_projector import (
    build_worker_projection,
    worker_setting_summaries,
)

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1.0.0"

__all__ = ["SettingsService"]


class SettingsService:
    def __init__(
        self,
        app_settings: Settings = settings,
        project_root: Path | None = None,
    ) -> None:
        self.app_settings = app_settings
        self.project_root = project_root or Path(__file__).resolve().parents[4]

    @staticmethod
    def _calculate_effective_backfill_interval(
        configured_interval: int,
        github_requests_per_minute: int,
        intake_pacing_seconds: int,
        github_token_count: int,
        firehose_pages: int,
        firehose_search_lanes: int,
        backfill_pages: int,
    ) -> int:
        return _calculate_effective_backfill_interval(
            configured_interval,
            github_requests_per_minute,
            intake_pacing_seconds,
            github_token_count,
            firehose_pages,
            firehose_search_lanes,
            backfill_pages,
        )

    def get_settings_summary(self) -> SettingsSummaryResponse:
        issues = validate_project_settings(self.app_settings)

        worker_projection, worker_issues = build_worker_projection(
            self.app_settings, self.project_root
        )
        issues.extend(worker_issues)

        openclaw_payload = load_openclaw_payload(self.app_settings, issues)
        gateway_target = resolve_openclaw_gateway_target(openclaw_payload)
        openclaw_settings = build_openclaw_setting_summaries(openclaw_payload, gateway_target)

        if any(issue.severity == "error" for issue in issues):
            _raise_validation_error(issues)

        logger.info("Settings summary generated successfully")

        return SettingsSummaryResponse(
            contract_version=CONTRACT_VERSION,
            ownership=_ownership_entries(),
            project_settings=project_setting_summaries(self.app_settings),
            worker_settings=worker_setting_summaries(worker_projection),
            openclaw_settings=openclaw_settings,
            validation=ConfigurationValidationResult(
                valid=True,
                issues=[issue for issue in issues if issue.severity == "warning"],
            ),
        )
