from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class WorkerRuntimeSettings(BaseModel):
    database_url: str
    runtime_dir: Path | None
    artifact_debug_mirror: bool
    workspace_dir: Path | None


class WorkerProviderSettings(BaseModel):
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
    idea_scout_interval_seconds: int
    idea_scout_per_page: int
    idea_scout_pages_per_run: int
    idea_scout_pacing_seconds: int
    idea_scout_window_days: int
    idea_scout_min_created_date: date
    bouncer_include_rules: tuple[str, ...]
    bouncer_exclude_rules: tuple[str, ...]
    analyst_selection_keywords: tuple[str, ...]


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
    GITHUB_PROVIDER_TOKENS: Annotated[tuple[str, ...], NoDecode] = ()
    GITHUB_REQUESTS_PER_MINUTE: int = 60
    INTAKE_PACING_SECONDS: int = 30
    FIREHOSE_INTERVAL_SECONDS: int = 3600
    FIREHOSE_PER_PAGE: int = 100
    FIREHOSE_PAGES: int = 3
    FIREHOSE_SEARCH_LANES: int = 1
    BACKFILL_INTERVAL_SECONDS: int = 21600
    BACKFILL_PER_PAGE: int = 100
    BACKFILL_PAGES: int = 2
    BACKFILL_WINDOW_DAYS: int = 30
    BACKFILL_MIN_CREATED_DATE: date = date(2008, 1, 1)
    IDEA_SCOUT_INTERVAL_SECONDS: int = 30
    IDEA_SCOUT_PER_PAGE: int = 100
    IDEA_SCOUT_PAGES_PER_RUN: int = 20
    IDEA_SCOUT_PACING_SECONDS: int = 2
    IDEA_SCOUT_WINDOW_DAYS: int = 30
    IDEA_SCOUT_MIN_CREATED_DATE: date = date(2008, 1, 1)
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

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
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
                    parsed = json.loads(candidate)
                    return tuple(str(part).strip() for part in parsed if str(part).strip())
                except (json.JSONDecodeError, ValueError):
                    pass
            return tuple(part.strip() for part in candidate.split(",") if part.strip())
        if isinstance(value, (list, tuple)):
            return tuple(str(part).strip() for part in value if str(part).strip())
        return value

    @field_validator("ANTHROPIC_API_KEY", mode="before")
    @classmethod
    def _normalize_anthropic_key(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return value

    @field_validator("GEMINI_API_KEY", mode="before")
    @classmethod
    def _normalize_gemini_key(cls, value: object) -> object:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
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

    @classmethod
    def model_post_init(cls, __context):
        """Validate configuration after all fields are set."""
        pass

    def __init__(self, **data):
        super().__init__(**data)
        if self.ANALYST_PROVIDER == "llm" and not self.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required when ANALYST_PROVIDER=llm")
        if self.ANALYST_PROVIDER == "gemini" and not self.gemini_api_key_values:
            raise ValueError("GEMINI_API_KEY or GEMINI_API_KEYS is required when ANALYST_PROVIDER=gemini")

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
        "FIREHOSE_SEARCH_LANES",
        "BACKFILL_INTERVAL_SECONDS",
        "BACKFILL_PER_PAGE",
        "BACKFILL_PAGES",
        "BACKFILL_WINDOW_DAYS",
        "IDEA_SCOUT_INTERVAL_SECONDS",
        "IDEA_SCOUT_PER_PAGE",
        "IDEA_SCOUT_PAGES_PER_RUN",
        "IDEA_SCOUT_PACING_SECONDS",
        "IDEA_SCOUT_WINDOW_DAYS",
    )
    @classmethod
    def _require_positive_numbers(cls, value: int) -> int:
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
            idea_scout_interval_seconds=self.IDEA_SCOUT_INTERVAL_SECONDS,
            idea_scout_per_page=self.IDEA_SCOUT_PER_PAGE,
            idea_scout_pages_per_run=self.IDEA_SCOUT_PAGES_PER_RUN,
            idea_scout_pacing_seconds=self.IDEA_SCOUT_PACING_SECONDS,
            idea_scout_window_days=self.IDEA_SCOUT_WINDOW_DAYS,
            idea_scout_min_created_date=self.IDEA_SCOUT_MIN_CREATED_DATE,
            bouncer_include_rules=self.BOUNCER_INCLUDE_RULES,
            bouncer_exclude_rules=self.BOUNCER_EXCLUDE_RULES,
            analyst_selection_keywords=self.ANALYST_SELECTION_KEYWORDS,
        )

    @property
    def openclaw_reference(self) -> WorkerOpenClawReferenceSettings:
        return WorkerOpenClawReferenceSettings(
            config_path=self.OPENCLAW_CONFIG_PATH,
            workspace_dir=self.OPENCLAW_WORKSPACE_DIR,
        )


settings = Settings()
