from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class BackendRuntimeSettings(BaseModel):
    api_v1_str: str
    database_url: str
    runtime_dir: Path | None
    artifact_debug_mirror: bool
    secret_key_configured: bool


class BackendProviderSettings(BaseModel):
    github_provider_token_configured: bool
    github_provider_token_count: int
    github_requests_per_minute: int
    intake_pacing_seconds: int
    firehose_interval_seconds: int
    firehose_per_page: int
    firehose_pages: int
    firehose_search_lanes: int
    backfill_interval_seconds: int
    backfill_per_page: int
    backfill_pages: int
    backfill_window_days: int
    backfill_min_created_date: date
    bouncer_include_rules: tuple[str, ...]
    bouncer_exclude_rules: tuple[str, ...]
    analyst_selection_keywords: tuple[str, ...]
    analyst_provider: str
    anthropic_api_key_configured: bool
    analyst_model_name: str
    gemini_api_key_configured: bool
    gemini_api_key_count: int
    gemini_base_url: str
    gemini_model_name: str


class OpenClawReferenceSettings(BaseModel):
    config_path: Path | None
    workspace_dir: Path | None


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    LOG_LEVEL: str = "INFO"
    API_V1_STR: str = "/api/v1"
    FRONTEND_PORT: int = 3000

    # Keep this as a string for the scaffold's local sqlite usage.
    DATABASE_URL: str = "sqlite:///../runtime/data/sqlite/agentic_workflow.db"
    SECRET_KEY: SecretStr | None = None
    AGENTIC_RUNTIME_DIR: Path | None = Path("../runtime")
    ARTIFACT_DEBUG_MIRROR: bool = False
    OPENCLAW_CONFIG_PATH: Path | None = Path("~/.openclaw/openclaw.json")
    OPENCLAW_WORKSPACE_DIR: Path | None = None
    GITHUB_PROVIDER_TOKEN: SecretStr | None = None
    GITHUB_PROVIDER_TOKENS: Annotated[tuple[str, ...], NoDecode] = ()
    GITHUB_REQUESTS_PER_MINUTE: int = 60
    INTAKE_PACING_SECONDS: int = 30
    FIREHOSE_INTERVAL_SECONDS: int = 3600
    FIREHOSE_PER_PAGE: int = 100
    FIREHOSE_PAGES: int = 3
    FIREHOSE_SEARCH_LANES: int = 1
    BACKFILL_INTERVAL_SECONDS: int = 21600
    EVENT_BRIDGE_POLL_INTERVAL_SECONDS: float = 2.0
    EVENT_STREAM_PING_INTERVAL_SECONDS: float = 15.0
    EVENT_STREAM_MAX_SUBSCRIBERS: int = 100
    EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE: int = 100
    BACKFILL_PER_PAGE: int = 100
    BACKFILL_PAGES: int = 2
    BACKFILL_WINDOW_DAYS: int = 30
    BACKFILL_MIN_CREATED_DATE: date = date(2008, 1, 1)
    OPERATIONAL_EVENT_RETENTION_DAYS: int = 30
    OPERATIONAL_RUN_RETENTION_DAYS: int = 30
    BOUNCER_INCLUDE_RULES: Annotated[tuple[str, ...], NoDecode] = ()
    BOUNCER_EXCLUDE_RULES: Annotated[tuple[str, ...], NoDecode] = ()
    ANALYST_SELECTION_KEYWORDS: Annotated[tuple[str, ...], NoDecode] = ()
    ANALYST_PROVIDER: str = "heuristic"
    ANTHROPIC_API_KEY: SecretStr | None = None
    ANALYST_MODEL_NAME: str = "claude-3-5-haiku-20241022"
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_API_KEYS: Annotated[tuple[str, ...], NoDecode] = ()
    GEMINI_BASE_URL: str = "https://api.haimaker.ai/v1"
    GEMINI_MODEL_NAME: str = "google/gemini-2.0-flash-001"
    OVERLORD_AUTO_REMEDIATION_ENABLED: bool = True
    OVERLORD_SAFE_PAUSE_ENABLED: bool = True
    OVERLORD_SAFE_RESUME_ENABLED: bool = True
    OVERLORD_STALE_STATE_CLEANUP_ENABLED: bool = True
    OVERLORD_EVALUATION_INTERVAL_SECONDS: int = 60
    OVERLORD_TELEGRAM_ENABLED: bool = False
    OVERLORD_TELEGRAM_BOT_TOKEN: SecretStr | None = None
    OVERLORD_TELEGRAM_CHAT_ID: str | None = None
    OVERLORD_TELEGRAM_MIN_SEVERITY: str = "error"
    OVERLORD_TELEGRAM_DAILY_DIGEST_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENVIRONMENT", "LOG_LEVEL", "API_V1_STR", "DATABASE_URL", mode="before")
    @classmethod
    def _normalize_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("SECRET_KEY", "GITHUB_PROVIDER_TOKEN", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OVERLORD_TELEGRAM_BOT_TOKEN", mode="before")
    @classmethod
    def _normalize_secret_strings(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return value

    @field_validator("OVERLORD_TELEGRAM_CHAT_ID", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return value

    @field_validator("GITHUB_PROVIDER_TOKENS", mode="before")
    @classmethod
    def _normalize_github_token_list(cls, value: object) -> tuple[str, ...] | object:
        if value is None:
            return ()
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return ()
            if candidate.startswith("["):
                try:
                    import json

                    parsed = json.loads(candidate)
                    return tuple(str(part).strip() for part in parsed if str(part).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            return tuple(part.strip() for part in candidate.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        return value

    @field_validator("GEMINI_API_KEYS", mode="before")
    @classmethod
    def _normalize_gemini_key_list(cls, value: object) -> tuple[str, ...] | object:
        if value is None:
            return ()
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return ()
            if candidate.startswith("["):
                try:
                    import json

                    parsed = json.loads(candidate)
                    return tuple(str(part).strip() for part in parsed if str(part).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            return tuple(part.strip() for part in candidate.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        return value

    @field_validator("ANALYST_PROVIDER", mode="before")
    @classmethod
    def _validate_analyst_provider(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate not in ("heuristic", "llm", "gemini"):
                raise ValueError("must be 'heuristic', 'llm', or 'gemini'")
            return candidate
        return value

    @field_validator("OVERLORD_TELEGRAM_MIN_SEVERITY", mode="before")
    @classmethod
    def _validate_overlord_severity(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip().lower()
            if candidate not in ("info", "warning", "error", "critical"):
                raise ValueError("must be one of: info, warning, error, critical")
            return candidate
        return value

    @field_validator(
        "AGENTIC_RUNTIME_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_WORKSPACE_DIR", mode="before"
    )
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
        "FRONTEND_PORT",
        "GITHUB_REQUESTS_PER_MINUTE",
        "INTAKE_PACING_SECONDS",
        "FIREHOSE_INTERVAL_SECONDS",
        "FIREHOSE_PER_PAGE",
        "FIREHOSE_PAGES",
        "FIREHOSE_SEARCH_LANES",
        "BACKFILL_INTERVAL_SECONDS",
        "EVENT_BRIDGE_POLL_INTERVAL_SECONDS",
        "EVENT_STREAM_PING_INTERVAL_SECONDS",
        "EVENT_STREAM_MAX_SUBSCRIBERS",
        "EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE",
        "BACKFILL_PER_PAGE",
        "BACKFILL_PAGES",
        "BACKFILL_WINDOW_DAYS",
        "OVERLORD_EVALUATION_INTERVAL_SECONDS",
    )
    @classmethod
    def _require_positive_numbers(cls, value: int | float) -> int | float:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator(
        "BOUNCER_INCLUDE_RULES",
        "BOUNCER_EXCLUDE_RULES",
        "ANALYST_SELECTION_KEYWORDS",
        mode="before",
    )
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
                    import json

                    parsed = json.loads(candidate)
                    return tuple(str(part).strip() for part in parsed if str(part).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            return tuple(part.strip() for part in candidate.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        return value

    @property
    def secret_key_value(self) -> str | None:
        if self.SECRET_KEY is None:
            return None
        return self.SECRET_KEY.get_secret_value()

    @property
    def github_provider_token_value(self) -> str | None:
        if self.GITHUB_PROVIDER_TOKEN is None:
            return None
        return self.GITHUB_PROVIDER_TOKEN.get_secret_value()

    @property
    def github_provider_token_values(self) -> tuple[str, ...]:
        configured: list[str] = []
        seen: set[str] = set()

        primary = self.github_provider_token_value
        if primary:
            configured.append(primary)
            seen.add(primary)

        for candidate in self.GITHUB_PROVIDER_TOKENS:
            token = str(candidate).strip()
            if not token or token in seen:
                continue
            configured.append(token)
            seen.add(token)

        return tuple(configured)

    @property
    def gemini_api_key_value(self) -> str | None:
        if self.GEMINI_API_KEY is None:
            return None
        return self.GEMINI_API_KEY.get_secret_value()

    @property
    def gemini_api_key_values(self) -> tuple[str, ...]:
        configured: list[str] = []
        seen: set[str] = set()

        primary = self.gemini_api_key_value
        if primary:
            configured.append(primary)
            seen.add(primary)

        for candidate in self.GEMINI_API_KEYS:
            key = str(candidate).strip()
            if not key or key in seen:
                continue
            configured.append(key)
            seen.add(key)

        return tuple(configured)

    @property
    def backend_runtime(self) -> BackendRuntimeSettings:
        return BackendRuntimeSettings(
            api_v1_str=self.API_V1_STR,
            database_url=self.DATABASE_URL,
            runtime_dir=self.AGENTIC_RUNTIME_DIR,
            artifact_debug_mirror=self.ARTIFACT_DEBUG_MIRROR,
            secret_key_configured=bool(self.secret_key_value),
        )

    @property
    def backend_provider(self) -> BackendProviderSettings:
        return BackendProviderSettings(
            github_provider_token_configured=bool(self.github_provider_token_values),
            github_provider_token_count=len(self.github_provider_token_values),
            github_requests_per_minute=self.GITHUB_REQUESTS_PER_MINUTE,
            intake_pacing_seconds=self.INTAKE_PACING_SECONDS,
            firehose_interval_seconds=self.FIREHOSE_INTERVAL_SECONDS,
            firehose_per_page=self.FIREHOSE_PER_PAGE,
            firehose_pages=self.FIREHOSE_PAGES,
            firehose_search_lanes=self.FIREHOSE_SEARCH_LANES,
            backfill_interval_seconds=self.BACKFILL_INTERVAL_SECONDS,
            backfill_per_page=self.BACKFILL_PER_PAGE,
            backfill_pages=self.BACKFILL_PAGES,
            backfill_window_days=self.BACKFILL_WINDOW_DAYS,
            backfill_min_created_date=self.BACKFILL_MIN_CREATED_DATE,
            bouncer_include_rules=self.BOUNCER_INCLUDE_RULES,
            bouncer_exclude_rules=self.BOUNCER_EXCLUDE_RULES,
            analyst_selection_keywords=self.ANALYST_SELECTION_KEYWORDS,
            analyst_provider=self.ANALYST_PROVIDER,
            anthropic_api_key_configured=bool(self.ANTHROPIC_API_KEY),
            analyst_model_name=self.ANALYST_MODEL_NAME,
            gemini_api_key_configured=bool(self.gemini_api_key_values),
            gemini_api_key_count=len(self.gemini_api_key_values),
            gemini_base_url=self.GEMINI_BASE_URL,
            gemini_model_name=self.GEMINI_MODEL_NAME,
        )

    @property
    def openclaw_reference(self) -> OpenClawReferenceSettings:
        return OpenClawReferenceSettings(
            config_path=self.OPENCLAW_CONFIG_PATH,
            workspace_dir=self.OPENCLAW_WORKSPACE_DIR,
        )

    @property
    def frontend_origins(self) -> list[str]:
        return [
            f"http://localhost:{self.FRONTEND_PORT}",
            f"http://127.0.0.1:{self.FRONTEND_PORT}",
        ]


settings = Settings()
