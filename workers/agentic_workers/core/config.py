from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerRuntimeSettings(BaseModel):
    database_url: str
    runtime_dir: Path | None
    artifact_debug_mirror: bool
    workspace_dir: Path | None


class WorkerProviderSettings(BaseModel):
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


class WorkerOpenClawReferenceSettings(BaseModel):
    config_path: Path | None
    workspace_dir: Path | None


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///../runtime/data/sqlite/agentic_workflow.db"
    AGENTIC_RUNTIME_DIR: Path | None = Path("../runtime")
    ARTIFACT_DEBUG_MIRROR: bool = False
    OPENCLAW_CONFIG_PATH: Path | None = Path("~/.openclaw/openclaw.json")
    OPENCLAW_WORKSPACE_DIR: Path | None = None
    GITHUB_PROVIDER_TOKEN: SecretStr | None = None
    GITHUB_REQUESTS_PER_MINUTE: int = 60
    INTAKE_PACING_SECONDS: int = 30
    FIREHOSE_INTERVAL_SECONDS: int = 3600
    FIREHOSE_PER_PAGE: int = 100
    FIREHOSE_PAGES: int = 3
    BACKFILL_INTERVAL_SECONDS: int = 21600
    BACKFILL_PER_PAGE: int = 100
    BACKFILL_PAGES: int = 2
    BACKFILL_WINDOW_DAYS: int = 30
    BACKFILL_MIN_CREATED_DATE: date = date(2008, 1, 1)
    BOUNCER_INCLUDE_RULES: tuple[str, ...] = ()
    BOUNCER_EXCLUDE_RULES: tuple[str, ...] = ()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENVIRONMENT", "LOG_LEVEL", "DATABASE_URL", mode="before")
    @classmethod
    def _normalize_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("GITHUB_PROVIDER_TOKEN", mode="before")
    @classmethod
    def _normalize_secret_strings(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return value

    @field_validator("AGENTIC_RUNTIME_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_WORKSPACE_DIR", mode="before")
    @classmethod
    def _expand_paths(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            return Path(candidate).expanduser()
        if isinstance(value, Path):
            return value.expanduser()
        return value

    @field_validator(
        "GITHUB_REQUESTS_PER_MINUTE",
        "INTAKE_PACING_SECONDS",
        "FIREHOSE_INTERVAL_SECONDS",
        "FIREHOSE_PER_PAGE",
        "FIREHOSE_PAGES",
        "BACKFILL_INTERVAL_SECONDS",
        "BACKFILL_PER_PAGE",
        "BACKFILL_PAGES",
        "BACKFILL_WINDOW_DAYS",
    )
    @classmethod
    def _require_positive_numbers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("BOUNCER_INCLUDE_RULES", "BOUNCER_EXCLUDE_RULES", mode="before")
    @classmethod
    def _normalize_rule_lists(cls, value: object) -> tuple[str, ...] | object:
        if value is None:
            return ()
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return ()
            if candidate.startswith("["):
                try:
                    parsed = json.loads(candidate)
                    return tuple(str(part).strip() for part in parsed if str(part).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            return tuple(part.strip() for part in candidate.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        return value

    @property
    def github_provider_token_value(self) -> str | None:
        if self.GITHUB_PROVIDER_TOKEN is None:
            return None
        return self.GITHUB_PROVIDER_TOKEN.get_secret_value()

    @property
    def runtime(self) -> WorkerRuntimeSettings:
        return WorkerRuntimeSettings(
            database_url=self.DATABASE_URL,
            runtime_dir=self.AGENTIC_RUNTIME_DIR,
            artifact_debug_mirror=self.ARTIFACT_DEBUG_MIRROR,
            workspace_dir=self.OPENCLAW_WORKSPACE_DIR,
        )

    @property
    def provider(self) -> WorkerProviderSettings:
        return WorkerProviderSettings(
            github_provider_token_configured=bool(self.github_provider_token_value),
            github_requests_per_minute=self.GITHUB_REQUESTS_PER_MINUTE,
            intake_pacing_seconds=self.INTAKE_PACING_SECONDS,
            firehose_interval_seconds=self.FIREHOSE_INTERVAL_SECONDS,
            firehose_per_page=self.FIREHOSE_PER_PAGE,
            firehose_pages=self.FIREHOSE_PAGES,
            backfill_interval_seconds=self.BACKFILL_INTERVAL_SECONDS,
            backfill_per_page=self.BACKFILL_PER_PAGE,
            backfill_pages=self.BACKFILL_PAGES,
            backfill_window_days=self.BACKFILL_WINDOW_DAYS,
            backfill_min_created_date=self.BACKFILL_MIN_CREATED_DATE,
            bouncer_include_rules=self.BOUNCER_INCLUDE_RULES,
            bouncer_exclude_rules=self.BOUNCER_EXCLUDE_RULES,
        )

    @property
    def openclaw_reference(self) -> WorkerOpenClawReferenceSettings:
        return WorkerOpenClawReferenceSettings(
            config_path=self.OPENCLAW_CONFIG_PATH,
            workspace_dir=self.OPENCLAW_WORKSPACE_DIR,
        )


settings = Settings()
