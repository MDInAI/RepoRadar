from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.agent_config import (
    AgentName,
    AgentConfigFieldResponse,
    AgentConfigResponse,
    AgentConfigUpdateRequest,
    AgentConfigUpdateResponse,
)

FieldKind = Literal["integer", "date", "csv", "text", "select"]


@dataclass(frozen=True, slots=True)
class ConfigFieldDefinition:
    key: str
    label: str
    description: str
    input_kind: FieldKind
    unit: str | None = None
    min_value: int | None = None
    placeholder: str | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentConfigDefinition:
    display_name: str
    summary: str
    apply_notes: tuple[str, ...]
    fields: tuple[ConfigFieldDefinition, ...]


AGENT_CONFIG_DEFINITIONS: dict[AgentName, AgentConfigDefinition] = {
    "firehose": AgentConfigDefinition(
        display_name="Firehose",
        summary="Control live discovery cadence, GitHub feed page budget, and pacing.",
        apply_notes=(
            "Saved to both backend/.env and workers/.env so the control surface stays in sync.",
            "Manual Run uses the new values immediately.",
            "Restart the always-on worker loop if you want interval changes to affect automatic scheduling right away.",
        ),
        fields=(
            ConfigFieldDefinition(
                key="FIREHOSE_INTERVAL_SECONDS",
                label="Interval",
                description="How long Firehose waits between automatic feed polls.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="FIREHOSE_PER_PAGE",
                label="Page size",
                description="How many repositories Firehose fetches from GitHub per page.",
                input_kind="integer",
                unit="repos",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="FIREHOSE_PAGES",
                label="Pages per mode",
                description="How many pages Firehose fetches for both NEW and TRENDING in each run.",
                input_kind="integer",
                unit="pages",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="GITHUB_REQUESTS_PER_MINUTE",
                label="GitHub request budget",
                description="Shared GitHub pacing cap used by Firehose and Backfill.",
                input_kind="integer",
                unit="req/min",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="INTAKE_PACING_SECONDS",
                label="Inter-job pacing",
                description="Shared pacing delay between intake jobs.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
        ),
    ),
    "backfill": AgentConfigDefinition(
        display_name="Backfill",
        summary="Control historical window size, page budget, and cadence for backfill scanning.",
        apply_notes=(
            "Saved to both backend/.env and workers/.env so the control surface stays in sync.",
            "Manual Run uses the new values immediately.",
            "Restart the always-on worker loop if you want interval changes to affect automatic scheduling right away.",
        ),
        fields=(
            ConfigFieldDefinition(
                key="BACKFILL_INTERVAL_SECONDS",
                label="Interval",
                description="How long Backfill waits between automatic historical scan cycles.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="BACKFILL_PER_PAGE",
                label="Page size",
                description="How many repositories Backfill requests from GitHub per page.",
                input_kind="integer",
                unit="repos",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="BACKFILL_PAGES",
                label="Pages per run",
                description="How many GitHub pages Backfill walks during one run.",
                input_kind="integer",
                unit="pages",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="BACKFILL_WINDOW_DAYS",
                label="Timeline window",
                description="How many creation-date days Backfill covers in each historical slice.",
                input_kind="integer",
                unit="days",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="BACKFILL_MIN_CREATED_DATE",
                label="Oldest repo date",
                description="Backfill will not scan older GitHub repositories than this creation date.",
                input_kind="date",
                placeholder="YYYY-MM-DD",
            ),
            ConfigFieldDefinition(
                key="GITHUB_REQUESTS_PER_MINUTE",
                label="GitHub request budget",
                description="Shared GitHub pacing cap used by Firehose and Backfill.",
                input_kind="integer",
                unit="req/min",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="INTAKE_PACING_SECONDS",
                label="Inter-job pacing",
                description="Shared pacing delay between intake jobs.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
        ),
    ),
    "bouncer": AgentConfigDefinition(
        display_name="Bouncer",
        summary="Control the Bouncer filter rules that allow or block repositories during triage.",
        apply_notes=(
            "Saved to both backend/.env and workers/.env so the control surface stays in sync.",
            "Manual Run uses the new values immediately.",
            "Restart the always-on worker loop if you want queue workers to adopt these values without waiting for a process restart.",
        ),
        fields=(
            ConfigFieldDefinition(
                key="BOUNCER_INCLUDE_RULES",
                label="Allow keywords",
                description="Comma-separated keywords or phrases that Bouncer should explicitly allow through triage.",
                input_kind="csv",
                placeholder="workflow, analytics, devtools",
            ),
            ConfigFieldDefinition(
                key="BOUNCER_EXCLUDE_RULES",
                label="Block keywords",
                description="Comma-separated keywords or phrases that Bouncer should explicitly reject during triage.",
                input_kind="csv",
                placeholder="games, homework, tutorial",
            ),
            ConfigFieldDefinition(
                key="INTAKE_PACING_SECONDS",
                label="Inter-job pacing",
                description="Shared pacing delay between queue jobs.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
        ),
    ),
    "analyst": AgentConfigDefinition(
        display_name="Analyst",
        summary="Control Analyst provider mode, model routing, and the shared intake settings that affect queue pickup.",
        apply_notes=(
            "Saved to both backend/.env and workers/.env so the control surface stays in sync.",
            "Manual Run uses the new provider and model settings immediately.",
            "Restart the always-on worker loop if you want queue workers to adopt these values without waiting for a process restart.",
            "API keys stay masked and must already be present in backend/.env and workers/.env when you select Anthropic or Gemini-compatible modes.",
        ),
        fields=(
            ConfigFieldDefinition(
                key="ANALYST_PROVIDER",
                label="Provider mode",
                description="Choose whether Analyst runs heuristically, with Anthropic, or through a Gemini-compatible endpoint.",
                input_kind="select",
                options=("heuristic", "llm", "gemini"),
            ),
            ConfigFieldDefinition(
                key="ANALYST_MODEL_NAME",
                label="Anthropic model",
                description="Anthropic model name used when Provider mode is set to llm.",
                input_kind="text",
                placeholder="claude-3-5-haiku-20241022",
            ),
            ConfigFieldDefinition(
                key="GEMINI_BASE_URL",
                label="Gemini-compatible base URL",
                description="Base URL used when Provider mode is set to gemini.",
                input_kind="text",
                placeholder="https://api.haimaker.ai/v1",
            ),
            ConfigFieldDefinition(
                key="GEMINI_MODEL_NAME",
                label="Gemini-compatible model",
                description="Model name used when Provider mode is set to gemini.",
                input_kind="text",
                placeholder="google/gemini-2.0-flash-001",
            ),
            ConfigFieldDefinition(
                key="GITHUB_REQUESTS_PER_MINUTE",
                label="GitHub request budget",
                description="Shared GitHub pacing cap that affects evidence gathering and intake throughput.",
                input_kind="integer",
                unit="req/min",
                min_value=1,
            ),
            ConfigFieldDefinition(
                key="INTAKE_PACING_SECONDS",
                label="Inter-job pacing",
                description="Shared pacing delay between queue-driven analyst jobs.",
                input_kind="integer",
                unit="seconds",
                min_value=1,
            ),
        ),
    ),
}


class AgentConfigService:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[3]
        self.backend_env_path = self.project_root / "backend" / ".env"
        self.worker_env_path = self.project_root / "workers" / ".env"

    def get_agent_config(self, agent_name: AgentName) -> AgentConfigResponse:
        definition = self._get_definition(agent_name)
        return self._build_response(agent_name, definition)

    def update_agent_config(
        self,
        agent_name: AgentName,
        request: AgentConfigUpdateRequest,
    ) -> AgentConfigUpdateResponse:
        definition = self._get_definition(agent_name)
        unknown_keys = sorted(set(request.values) - {field.key for field in definition.fields})
        if unknown_keys:
            raise AppError(
                message="The update payload contains unsupported agent settings.",
                code="agent_config_unknown_fields",
                status_code=400,
                details={"keys": unknown_keys},
            )

        backend_values = self._load_env_values(self.backend_env_path)
        worker_values = self._load_env_values(self.worker_env_path)
        updates: dict[str, str] = {}

        for field in definition.fields:
            incoming = request.values.get(field.key, self._resolve_value(field.key, backend_values, worker_values))
            updates[field.key] = self._normalize_value(field, incoming)

        self._write_env_updates(self.backend_env_path, updates)
        self._write_env_updates(self.worker_env_path, updates)

        response = self._build_response(agent_name, definition)
        return AgentConfigUpdateResponse(
            **response.model_dump(),
            message=(
                f"Saved {definition.display_name} runtime settings. Manual runs use the new values "
                "immediately; restart the always-on worker loop to apply cadence changes to auto-runs."
            ),
        )

    def _get_definition(self, agent_name: AgentName) -> AgentConfigDefinition:
        if agent_name not in AGENT_CONFIG_DEFINITIONS:
            raise AppError(
                message=f"Agent '{agent_name}' does not expose editable runtime settings yet.",
                code="agent_config_not_found",
                status_code=404,
            )
        return AGENT_CONFIG_DEFINITIONS[agent_name]

    def _build_response(
        self,
        agent_name: AgentName,
        definition: AgentConfigDefinition,
    ) -> AgentConfigResponse:
        backend_values = self._load_env_values(self.backend_env_path)
        worker_values = self._load_env_values(self.worker_env_path)
        fields = [
            AgentConfigFieldResponse(
                key=field.key,
                label=field.label,
                description=field.description,
                input_kind=field.input_kind,
                value=self._resolve_value(field.key, backend_values, worker_values),
                options=list(field.options),
                unit=field.unit,
                min_value=field.min_value,
                placeholder=field.placeholder,
            )
            for field in definition.fields
        ]

        return AgentConfigResponse(
            agent_name=agent_name,
            display_name=definition.display_name,
            editable=bool(definition.fields),
            summary=definition.summary,
            apply_notes=list(definition.apply_notes),
            fields=fields,
        )

    def _load_env_values(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        loaded = dotenv_values(path)
        return {key: value.strip() for key, value in loaded.items() if value is not None}

    def _resolve_value(
        self,
        key: str,
        backend_values: dict[str, str],
        worker_values: dict[str, str],
    ) -> str:
        if key in worker_values:
            return worker_values[key]
        if key in backend_values:
            return backend_values[key]

        default = Settings.model_fields[key].default
        if isinstance(default, date):
            return default.isoformat()
        if isinstance(default, tuple):
            return ", ".join(str(item) for item in default if str(item).strip())
        return str(default)

    def _normalize_value(self, field: ConfigFieldDefinition, raw_value: str) -> str:
        candidate = raw_value.strip()
        if "\n" in candidate or "\r" in candidate:
            raise AppError(
                message=f"{field.label} must be a single-line value.",
                code="agent_config_invalid_multiline",
                status_code=400,
                details={"field": field.key},
            )

        if field.input_kind == "integer":
            try:
                parsed = int(candidate)
            except ValueError as exc:
                raise AppError(
                    message=f"{field.label} must be a positive integer.",
                    code="agent_config_invalid_integer",
                    status_code=400,
                    details={"field": field.key},
                ) from exc
            min_value = field.min_value or 1
            if parsed < min_value:
                raise AppError(
                    message=f"{field.label} must be at least {min_value}.",
                    code="agent_config_invalid_integer",
                    status_code=400,
                    details={"field": field.key, "min_value": min_value},
                )
            return str(parsed)

        if field.input_kind == "date":
            try:
                return date.fromisoformat(candidate).isoformat()
            except ValueError as exc:
                raise AppError(
                    message=f"{field.label} must be an ISO date in YYYY-MM-DD format.",
                    code="agent_config_invalid_date",
                    status_code=400,
                    details={"field": field.key},
                ) from exc

        if field.input_kind == "csv":
            if not candidate:
                return ""
            normalized = [part.strip() for part in candidate.split(",") if part.strip()]
            return ", ".join(normalized)

        if field.input_kind == "text":
            return candidate

        if field.input_kind == "select":
            normalized = candidate.lower()
            if normalized not in field.options:
                raise AppError(
                    message=f"{field.label} must be one of: {', '.join(field.options)}.",
                    code="agent_config_invalid_option",
                    status_code=400,
                    details={"field": field.key, "options": list(field.options)},
                )
            return normalized

        raise AppError(
            message=f"Unsupported config field type for '{field.key}'.",
            code="agent_config_invalid_field_type",
            status_code=500,
        )

    def _write_env_updates(self, path: Path, updates: dict[str, str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        remaining = dict(updates)
        output: list[str] = []

        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line)
                continue

            key, _ = line.split("=", 1)
            key = key.strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
            else:
                output.append(line)

        if remaining:
            if output and output[-1].strip():
                output.append("")
            for key in sorted(remaining):
                output.append(f"{key}={remaining[key]}")

        path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
