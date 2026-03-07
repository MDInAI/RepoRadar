from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendRuntimeSettings(BaseModel):
    api_v1_str: str
    database_url: str
    runtime_dir: Path | None
    secret_key_configured: bool


class BackendProviderSettings(BaseModel):
    github_provider_token_configured: bool
    github_requests_per_minute: int
    intake_pacing_seconds: int


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
    OPENCLAW_CONFIG_PATH: Path | None = Path("~/.openclaw/openclaw.json")
    OPENCLAW_WORKSPACE_DIR: Path | None = None
    GITHUB_PROVIDER_TOKEN: SecretStr | None = None
    GITHUB_REQUESTS_PER_MINUTE: int = 60
    INTAKE_PACING_SECONDS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
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

    @field_validator("SECRET_KEY", "GITHUB_PROVIDER_TOKEN", mode="before")
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

    @field_validator("FRONTEND_PORT", "GITHUB_REQUESTS_PER_MINUTE", "INTAKE_PACING_SECONDS")
    @classmethod
    def _require_positive_numbers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
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
    def backend_runtime(self) -> BackendRuntimeSettings:
        return BackendRuntimeSettings(
            api_v1_str=self.API_V1_STR,
            database_url=self.DATABASE_URL,
            runtime_dir=self.AGENTIC_RUNTIME_DIR,
            secret_key_configured=bool(self.secret_key_value),
        )

    @property
    def backend_provider(self) -> BackendProviderSettings:
        return BackendProviderSettings(
            github_provider_token_configured=bool(self.github_provider_token_value),
            github_requests_per_minute=self.GITHUB_REQUESTS_PER_MINUTE,
            intake_pacing_seconds=self.INTAKE_PACING_SECONDS,
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
