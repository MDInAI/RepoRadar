from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import os
from pathlib import Path
from typing import Any

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.schemas.settings import (
    ConfigurationOwnership,
    ConfigurationValidationIssue,
    ConfigurationValidationResult,
    MaskedSettingSummary,
    SettingsSummaryResponse,
)
from app.services.openclaw.config_service import (
    OpenClawConfigError,
    OpenClawConfigReadError,
    extract_default_model,
    extract_gateway_allow_insecure_tls,
    extract_gateway_config,
    load_openclaw_config,
)
from app.services.openclaw.transport import (
    CONFIG_VALIDATION_STATUS_CODE,
    GatewayTargetInput,
    GatewayTargetResolution,
    resolve_gateway_target_from_input,
)

CONTRACT_VERSION = "1.0.0"
_FIREHOSE_MODE_COUNT = 2
_DEFAULT_FIREHOSE_PAGES = 3


@dataclass(frozen=True, slots=True)
class WorkerSettingsProjection:
    database_url: str
    runtime_dir: Path
    workspace_dir: Path | None
    github_provider_token_configured: bool
    github_requests_per_minute: int
    intake_pacing_seconds: int
    firehose_pages: int
    backfill_interval_seconds: int
    backfill_per_page: int
    backfill_pages: int
    backfill_window_days: int
    backfill_min_created_date: date
    source: str
    overrides_loaded: bool


class SettingsService:
    def __init__(
        self,
        app_settings: Settings = settings,
        project_root: Path | None = None,
    ) -> None:
        self.app_settings = app_settings
        self.project_root = project_root or Path(__file__).resolve().parents[3]

    def get_settings_summary(self) -> SettingsSummaryResponse:
        issues = self._validate_project_settings()
        worker_projection, worker_issues = self._build_worker_projection()
        issues.extend(worker_issues)
        openclaw_payload = self._load_openclaw_payload(issues)
        gateway_target = self._resolve_openclaw_gateway_target(openclaw_payload)
        openclaw_settings = self._build_openclaw_setting_summaries(
            openclaw_payload,
            gateway_target,
        )

        if any(issue.severity == "error" for issue in issues):
            self._raise_validation_error(issues)

        return SettingsSummaryResponse(
            contract_version=CONTRACT_VERSION,
            ownership=self._ownership_entries(),
            project_settings=self._project_setting_summaries(),
            worker_settings=self._worker_setting_summaries(worker_projection),
            openclaw_settings=openclaw_settings,
            validation=ConfigurationValidationResult(
                valid=True,
                issues=[issue for issue in issues if issue.severity == "warning"],
            ),
        )

    def _validate_project_settings(self) -> list[ConfigurationValidationIssue]:
        issues: list[ConfigurationValidationIssue] = []

        if not self.app_settings.DATABASE_URL.strip():
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

        runtime_dir = self.app_settings.AGENTIC_RUNTIME_DIR
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

        workspace_dir = self.app_settings.OPENCLAW_WORKSPACE_DIR
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

        return issues

    def _build_worker_projection(
        self,
    ) -> tuple[WorkerSettingsProjection, list[ConfigurationValidationIssue]]:
        issues: list[ConfigurationValidationIssue] = []
        worker_env_path = self.project_root / "workers" / ".env"
        overrides = self._parse_env_file(worker_env_path) if worker_env_path.is_file() else {}
        applied_override_keys: set[str] = set()

        database_url = self._env_override(
            overrides,
            "DATABASE_URL",
            self.app_settings.DATABASE_URL,
            applied_override_keys=applied_override_keys,
        )
        runtime_dir = self._path_override(
            overrides,
            "AGENTIC_RUNTIME_DIR",
            self.app_settings.AGENTIC_RUNTIME_DIR,
            applied_override_keys=applied_override_keys,
        )
        workspace_dir = self._optional_path_override(
            overrides,
            "OPENCLAW_WORKSPACE_DIR",
            self.app_settings.OPENCLAW_WORKSPACE_DIR,
            applied_override_keys=applied_override_keys,
        )
        github_token = self._optional_string_override(
            overrides,
            "GITHUB_PROVIDER_TOKEN",
            self.app_settings.github_provider_token_value,
            applied_override_keys=applied_override_keys,
        )
        requests_per_minute = self._int_override(
            overrides,
            "GITHUB_REQUESTS_PER_MINUTE",
            self.app_settings.GITHUB_REQUESTS_PER_MINUTE,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        intake_pacing_seconds = self._int_override(
            overrides,
            "INTAKE_PACING_SECONDS",
            self.app_settings.INTAKE_PACING_SECONDS,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        firehose_pages = self._int_override(
            overrides,
            "FIREHOSE_PAGES",
            self._process_env_int("FIREHOSE_PAGES", default=_DEFAULT_FIREHOSE_PAGES),
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        backfill_interval_seconds = self._int_override(
            overrides,
            "BACKFILL_INTERVAL_SECONDS",
            self.app_settings.BACKFILL_INTERVAL_SECONDS,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        backfill_per_page = self._int_override(
            overrides,
            "BACKFILL_PER_PAGE",
            self.app_settings.BACKFILL_PER_PAGE,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        backfill_pages = self._int_override(
            overrides,
            "BACKFILL_PAGES",
            self.app_settings.BACKFILL_PAGES,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        backfill_window_days = self._int_override(
            overrides,
            "BACKFILL_WINDOW_DAYS",
            self.app_settings.BACKFILL_WINDOW_DAYS,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        backfill_min_created_date = self._date_override(
            overrides,
            "BACKFILL_MIN_CREATED_DATE",
            self.app_settings.BACKFILL_MIN_CREATED_DATE,
            issues=issues,
            applied_override_keys=applied_override_keys,
        )
        source = "workers-env" if applied_override_keys else "shared-project-env"

        projection = WorkerSettingsProjection(
            database_url=database_url,
            runtime_dir=runtime_dir,
            workspace_dir=workspace_dir,
            github_provider_token_configured=bool(github_token),
            github_requests_per_minute=requests_per_minute,
            intake_pacing_seconds=intake_pacing_seconds,
            firehose_pages=firehose_pages,
            backfill_interval_seconds=backfill_interval_seconds,
            backfill_per_page=backfill_per_page,
            backfill_pages=backfill_pages,
            backfill_window_days=backfill_window_days,
            backfill_min_created_date=backfill_min_created_date,
            source=source,
            overrides_loaded=bool(applied_override_keys),
        )

        issues.extend(self._validate_worker_settings(projection))
        issues.extend(self._detect_worker_drift(projection))

        return projection, issues

    def _load_openclaw_payload(
        self,
        issues: list[ConfigurationValidationIssue],
    ) -> dict[str, Any]:
        if not self.app_settings.OPENCLAW_CONFIG_PATH:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="OPENCLAW_CONFIG_PATH",
                    owner="openclaw",
                    code="openclaw_config_missing",
                    message="OpenClaw config path is not configured.",
                    source="openclaw-config",
                )
            )
            self._raise_validation_error(issues)

        config_path = self.app_settings.OPENCLAW_CONFIG_PATH.expanduser()
        if not config_path.is_file():
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="OPENCLAW_CONFIG_PATH",
                    owner="openclaw",
                    code="openclaw_config_missing",
                    message="OpenClaw config file was not found.",
                    source="openclaw-config",
                )
            )
            self._raise_validation_error(issues)

        try:
            loaded = load_openclaw_config(config_path)
        except OpenClawConfigReadError as exc:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="OPENCLAW_CONFIG_PATH",
                    owner="openclaw",
                    code="openclaw_config_unreadable",
                    message=f"OpenClaw config is unreadable: {exc}",
                    source="openclaw-config",
                )
            )
            self._raise_validation_error(issues)
        except OpenClawConfigError as exc:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="OPENCLAW_CONFIG_PATH",
                    owner="openclaw",
                    code="openclaw_config_invalid_json",
                    message=f"OpenClaw config is not valid JSON/JSON5: {exc}",
                    source="openclaw-config",
                )
            )
            self._raise_validation_error(issues)

        if not isinstance(loaded, dict):
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="OPENCLAW_CONFIG_PATH",
                    owner="openclaw",
                    code="openclaw_config_invalid_shape",
                    message="OpenClaw config must be a JSON object.",
                    source="openclaw-config",
                )
            )
            self._raise_validation_error(issues)

        gateway = extract_gateway_config(loaded)
        default_model = extract_default_model(loaded)

        if not gateway.url:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="gateway.url",
                    owner="gateway",
                    code="gateway_url_missing",
                    message="OpenClaw config must define gateway.url for backend mediation.",
                    source="openclaw-config",
                )
            )

        if not gateway.token:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="gateway.auth.token",
                    owner="gateway",
                    code="gateway_token_missing",
                    message="OpenClaw config must define gateway.auth.token.",
                    source="openclaw-config",
                )
            )

        if not default_model:
            issues.append(
                ConfigurationValidationIssue(
                    severity="error",
                    field="agents.defaults.model.primary",
                    owner="openclaw",
                    code="default_model_missing",
                    message=(
                        "OpenClaw config must define agents.defaults.model.primary "
                        "(or a legacy string model)."
                    ),
                    source="openclaw-config",
                )
            )

        if any(issue.severity == "error" for issue in issues):
            self._raise_validation_error(issues)

        return loaded

    def _resolve_openclaw_gateway_target(
        self,
        payload: dict[str, Any],
    ) -> GatewayTargetResolution:
        gateway = extract_gateway_config(payload)
        return resolve_gateway_target_from_input(
            GatewayTargetInput(
                url=gateway.url,
                token=gateway.token,
                allow_insecure_tls=gateway.allow_insecure_tls,
                source="openclaw-config",
                placeholder_source="openclaw-config-missing",
                configured_notes=(
                    "Gateway transport is normalized from OpenClaw-owned config and exposed as a masked summary only.",
                ),
            )
        )

    def _project_setting_summaries(self) -> list[MaskedSettingSummary]:
        runtime = self.app_settings.backend_runtime
        provider = self.app_settings.backend_provider
        reference = self.app_settings.openclaw_reference

        effective_backfill_interval = self._calculate_effective_backfill_interval(
            provider.backfill_interval_seconds,
            provider.github_requests_per_minute,
            provider.intake_pacing_seconds,
            self._process_env_int("FIREHOSE_PAGES", default=_DEFAULT_FIREHOSE_PAGES),
            provider.backfill_pages,
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
                notes=["Workspace context remains separate from Gateway and OpenClaw control-plane state."],
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

    def _worker_setting_summaries(
        self,
        worker: WorkerSettingsProjection,
    ) -> list[MaskedSettingSummary]:
        source_notes = (
            "Worker-specific overrides are loaded from workers/.env."
            if worker.overrides_loaded
            else "Workers inherit the shared project env when launched via scripts/dev.sh."
        )
        workspace_value = str(worker.workspace_dir) if worker.workspace_dir else None

        worker_effective_backfill_interval = self._calculate_effective_backfill_interval(
            worker.backfill_interval_seconds,
            worker.github_requests_per_minute,
            worker.intake_pacing_seconds,
            worker.firehose_pages,
            worker.backfill_pages,
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
        ]

    def _build_openclaw_setting_summaries(
        self,
        payload: dict[str, Any],
        gateway_target: GatewayTargetResolution,
    ) -> list[MaskedSettingSummary]:
        gateway_config = self._as_dict(payload.get("gateway"))
        auth_config = self._as_dict(gateway_config.get("auth"))
        default_model = extract_default_model(payload)
        channels = self._as_dict(payload.get("channels"))
        configured_channels = sorted(channels.keys())
        remote_config = self._as_dict(gateway_config.get("remote"))

        return [
            MaskedSettingSummary(
                key="gateway.url",
                label="Gateway URL",
                owner="gateway",
                source="openclaw-config",
                configured=gateway_target.configured,
                required=True,
                value=gateway_target.url,
                notes=["Normalized with shared Gateway URL validation logic."],
            ),
            MaskedSettingSummary(
                key="gateway.auth.token",
                label="Gateway auth token",
                owner="gateway",
                source="openclaw-config",
                configured=bool(self._as_string(auth_config.get("token"))),
                required=True,
                secret=True,
                value="configured" if self._as_string(auth_config.get("token")) else "missing",
                notes=["Gateway credentials stay OpenClaw-owned and backend-masked."],
            ),
            MaskedSettingSummary(
                key="gateway.allowInsecureTls",
                label="Gateway insecure TLS flag",
                owner="gateway",
                source="openclaw-config",
                configured=(
                    "allowInsecureTls" in gateway_config
                    or "allowInsecureTls" in remote_config
                ),
                required=False,
                value=str(extract_gateway_allow_insecure_tls(gateway_config)).lower(),
                notes=["Transport flags are summarized for inspection but not editable from the browser."],
            ),
            MaskedSettingSummary(
                key="agents.defaults.model",
                label="Default agent model",
                owner="openclaw",
                source="openclaw-config",
                configured=bool(default_model),
                required=True,
                value=default_model,
                notes=[
                    "Model defaults remain OpenClaw-native conventions rather than project env.",
                    "Object-shaped defaults use agents.defaults.model.primary as the displayed value.",
                ],
            ),
            MaskedSettingSummary(
                key="channels",
                label="Configured OpenClaw channels",
                owner="openclaw",
                source="openclaw-config",
                configured=bool(configured_channels),
                required=False,
                value=", ".join(configured_channels) if configured_channels else "none",
                notes=["Only channel names are surfaced; channel secrets remain hidden."],
            ),
        ]

    def _ownership_entries(self) -> list[ConfigurationOwnership]:
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
                notes=["Workspace files remain separate from Gateway and OpenClaw control-plane ownership."],
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
                notes=["Project-owned settings must never duplicate OpenClaw-native secrets or browser-exposed config."],
            ),
        ]

    def _raise_validation_error(
        self,
        issues: list[ConfigurationValidationIssue],
    ) -> None:
        validation = ConfigurationValidationResult(valid=False, issues=issues)
        raise AppError(
            message="Configuration validation failed.",
            code="settings_validation_failed",
            status_code=CONFIG_VALIDATION_STATUS_CODE,
            details={"validation": validation.model_dump()},
        )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _as_string(value: Any) -> str | None:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return None

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return False

    def _validate_worker_settings(
        self,
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
        self,
        worker: WorkerSettingsProjection,
    ) -> list[ConfigurationValidationIssue]:
        if not worker.overrides_loaded:
            return []

        issues: list[ConfigurationValidationIssue] = []
        comparisons = [
            (
                "workers.DATABASE_URL",
                "agentic-workflow",
                worker.database_url,
                self.app_settings.DATABASE_URL,
                "worker_database_url_differs",
                "Worker database URL differs from the backend process view.",
            ),
            (
                "workers.AGENTIC_RUNTIME_DIR",
                "agentic-workflow",
                str(worker.runtime_dir) if worker.runtime_dir else "",
                str(self.app_settings.AGENTIC_RUNTIME_DIR) if self.app_settings.AGENTIC_RUNTIME_DIR else "",
                "worker_runtime_dir_differs",
                "Worker runtime directory differs from the backend process view.",
            ),
            (
                "workers.OPENCLAW_WORKSPACE_DIR",
                "workspace",
                str(worker.workspace_dir) if worker.workspace_dir else "",
                str(self.app_settings.OPENCLAW_WORKSPACE_DIR)
                if self.app_settings.OPENCLAW_WORKSPACE_DIR
                else "",
                "worker_workspace_dir_differs",
                "Worker workspace directory differs from the backend process view.",
            ),
            (
                "workers.GITHUB_PROVIDER_TOKEN",
                "agentic-workflow",
                str(worker.github_provider_token_configured).lower(),
                str(self.app_settings.backend_provider.github_provider_token_configured).lower(),
                "worker_github_provider_token_differs",
                "Worker GitHub provider token configured-state differs from the backend process view.",
            ),
            (
                "workers.GITHUB_REQUESTS_PER_MINUTE",
                "agentic-workflow",
                str(worker.github_requests_per_minute),
                str(self.app_settings.GITHUB_REQUESTS_PER_MINUTE),
                "worker_github_requests_per_minute_differs",
                "Worker GitHub request budget differs from the backend process view.",
            ),
            (
                "workers.INTAKE_PACING_SECONDS",
                "agentic-workflow",
                str(worker.intake_pacing_seconds),
                str(self.app_settings.INTAKE_PACING_SECONDS),
                "worker_intake_pacing_seconds_differs",
                "Worker intake pacing interval differs from the backend process view.",
            ),
            (
                "workers.BACKFILL_INTERVAL_SECONDS",
                "agentic-workflow",
                str(worker.backfill_interval_seconds),
                str(self.app_settings.BACKFILL_INTERVAL_SECONDS),
                "worker_backfill_interval_seconds_differs",
                "Worker backfill interval differs from the backend process view.",
            ),
            (
                "workers.BACKFILL_PER_PAGE",
                "agentic-workflow",
                str(worker.backfill_per_page),
                str(self.app_settings.BACKFILL_PER_PAGE),
                "worker_backfill_per_page_differs",
                "Worker backfill page size differs from the backend process view.",
            ),
            (
                "workers.BACKFILL_PAGES",
                "agentic-workflow",
                str(worker.backfill_pages),
                str(self.app_settings.BACKFILL_PAGES),
                "worker_backfill_pages_differs",
                "Worker backfill pages-per-run differs from the backend process view.",
            ),
            (
                "workers.BACKFILL_WINDOW_DAYS",
                "agentic-workflow",
                str(worker.backfill_window_days),
                str(self.app_settings.BACKFILL_WINDOW_DAYS),
                "worker_backfill_window_days_differs",
                "Worker backfill window size differs from the backend process view.",
            ),
            (
                "workers.BACKFILL_MIN_CREATED_DATE",
                "agentic-workflow",
                worker.backfill_min_created_date.isoformat(),
                self.app_settings.BACKFILL_MIN_CREATED_DATE.isoformat(),
                "worker_backfill_min_created_date_differs",
                "Worker backfill oldest created-date cutoff differs from the backend process view.",
            ),
        ]

        for field, owner, worker_value, backend_value, code, message in comparisons:
            if worker_value != backend_value:
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

    @staticmethod
    def _calculate_effective_intake_pacing(
        github_requests_per_minute: int,
        intake_pacing_seconds: int,
    ) -> int:
        request_budget_floor = math.ceil(60 / github_requests_per_minute)
        return max(intake_pacing_seconds, request_budget_floor)

    @classmethod
    def _calculate_effective_backfill_interval(
        cls,
        configured_interval: int,
        github_requests_per_minute: int,
        intake_pacing_seconds: int,
        firehose_pages: int,
        backfill_pages: int,
    ) -> int:
        if configured_interval <= 0:
            raise ValueError("backfill_interval_seconds must be greater than zero")

        effective_pacing = cls._calculate_effective_intake_pacing(
            github_requests_per_minute,
            intake_pacing_seconds,
        )
        firehose_requests = _FIREHOSE_MODE_COUNT * firehose_pages
        min_cycle = (firehose_requests + backfill_pages) * effective_pacing
        return max(configured_interval, min_cycle)

    @staticmethod
    def _parse_env_file(path: Path) -> dict[str, str]:
        from dotenv import dotenv_values

        loaded = dotenv_values(path)
        return {k: v.strip() for k, v in loaded.items() if v is not None}

    @staticmethod
    def _process_env_int(key: str, *, default: int) -> int:
        raw_value = os.getenv(key)
        if raw_value is None:
            return default
        try:
            return int(raw_value)
        except ValueError:
            return default

    @staticmethod
    def _env_override(
        overrides: dict[str, str],
        key: str,
        fallback: str,
        *,
        applied_override_keys: set[str],
    ) -> str:
        if key in overrides and key not in os.environ:
            applied_override_keys.add(key)
            return overrides[key].strip()
        return fallback.strip()

    @staticmethod
    def _optional_string_override(
        overrides: dict[str, str],
        key: str,
        fallback: str | None,
        *,
        applied_override_keys: set[str],
    ) -> str | None:
        if key in overrides and key not in os.environ:
            applied_override_keys.add(key)
            candidate = overrides[key]
        else:
            candidate = fallback or ""
        candidate = candidate.strip()
        return candidate or None

    @staticmethod
    def _path_override(
        overrides: dict[str, str],
        key: str,
        fallback: Path | None,
        *,
        applied_override_keys: set[str],
    ) -> Path | None:
        if key not in overrides or key in os.environ:
            return fallback

        applied_override_keys.add(key)
        candidate = overrides[key].strip()
        if not candidate:
            return None
        return Path(candidate).expanduser()

    @staticmethod
    def _optional_path_override(
        overrides: dict[str, str],
        key: str,
        fallback: Path | None,
        *,
        applied_override_keys: set[str],
    ) -> Path | None:
        if key not in overrides or key in os.environ:
            return fallback
        applied_override_keys.add(key)
        candidate = overrides[key]
        candidate = candidate.strip()
        if not candidate:
            return None
        return Path(candidate).expanduser()

    @staticmethod
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

        applied_override_keys.add(key)
        return parsed

    @staticmethod
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

        applied_override_keys.add(key)
        return parsed
