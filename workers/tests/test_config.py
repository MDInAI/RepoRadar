from __future__ import annotations

from pathlib import Path

from agentic_workers.core.config import Settings


def test_worker_settings_expose_project_and_openclaw_groups(tmp_path: Path) -> None:
    settings = Settings(
        DATABASE_URL="sqlite:///../runtime/data/sqlite/agentic_workflow.db",
        AGENTIC_RUNTIME_DIR=tmp_path / "runtime",
        OPENCLAW_WORKSPACE_DIR=tmp_path / "workspace",
        OPENCLAW_CONFIG_PATH=tmp_path / "openclaw.json",
        GITHUB_PROVIDER_TOKEN="worker-provider-token",
        GITHUB_REQUESTS_PER_MINUTE=25,
        INTAKE_PACING_SECONDS=15,
    )

    assert settings.runtime.database_url == "sqlite:///../runtime/data/sqlite/agentic_workflow.db"
    assert settings.runtime.runtime_dir == tmp_path / "runtime"
    assert settings.runtime.workspace_dir == tmp_path / "workspace"
    assert settings.provider.github_provider_token_configured is True
    assert settings.provider.github_requests_per_minute == 25
    assert settings.provider.intake_pacing_seconds == 15
    assert settings.openclaw_reference.config_path == tmp_path / "openclaw.json"


def test_worker_settings_do_not_assume_machine_specific_workspace_defaults() -> None:
    settings = Settings()

    assert settings.OPENCLAW_WORKSPACE_DIR is None
    assert settings.runtime.workspace_dir is None
