from __future__ import annotations

from datetime import date
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
        BACKFILL_INTERVAL_SECONDS=7200,
        BACKFILL_PER_PAGE=50,
        BACKFILL_PAGES=4,
        BACKFILL_WINDOW_DAYS=14,
        BACKFILL_MIN_CREATED_DATE=date(2015, 1, 1),
        BOUNCER_INCLUDE_RULES="saas, developer tools",
        BOUNCER_EXCLUDE_RULES=("gaming", "tutorial"),
    )

    assert settings.runtime.database_url == "sqlite:///../runtime/data/sqlite/agentic_workflow.db"
    assert settings.runtime.runtime_dir == tmp_path / "runtime"
    assert settings.runtime.workspace_dir == tmp_path / "workspace"
    assert settings.provider.github_provider_token_configured is True
    assert settings.provider.github_requests_per_minute == 25
    assert settings.provider.intake_pacing_seconds == 15
    assert settings.provider.backfill_interval_seconds == 7200
    assert settings.provider.backfill_per_page == 50
    assert settings.provider.backfill_pages == 4
    assert settings.provider.backfill_window_days == 14
    assert settings.provider.backfill_min_created_date == date(2015, 1, 1)
    assert settings.provider.bouncer_include_rules == ("saas", "developer tools")
    assert settings.provider.bouncer_exclude_rules == ("gaming", "tutorial")
    assert settings.openclaw_reference.config_path == tmp_path / "openclaw.json"


def test_worker_settings_do_not_assume_machine_specific_workspace_defaults() -> None:
    settings = Settings()

    assert settings.OPENCLAW_WORKSPACE_DIR is None
    assert settings.runtime.workspace_dir is None
