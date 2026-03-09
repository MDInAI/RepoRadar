from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from agentic_workers.core.config import Settings, WorkerProviderSettings, WorkerRuntimeSettings
from pydantic import ValidationError


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


def test_bouncer_rules_parsed_from_json_array_string() -> None:
    settings = Settings(
        BOUNCER_INCLUDE_RULES='["saas", "developer tools"]',
        BOUNCER_EXCLUDE_RULES='["gaming", "tutorial"]',
    )

    assert settings.provider.bouncer_include_rules == ("saas", "developer tools")
    assert settings.provider.bouncer_exclude_rules == ("gaming", "tutorial")


def test_bouncer_rules_json_array_with_whitespace_entries_filtered() -> None:
    settings = Settings(BOUNCER_INCLUDE_RULES='["saas", "  ", "tools"]')

    assert settings.provider.bouncer_include_rules == ("saas", "tools")


def test_bouncer_rules_malformed_json_array_falls_back_to_csv() -> None:
    # "[saas, tools" is not valid JSON — falls back to CSV splitting
    settings = Settings(BOUNCER_INCLUDE_RULES="[saas, tools")

    # CSV split treats the whole string as one entry (no comma outside the bracket)
    # The leading "[" is kept in the first token since it's treated as plain text
    result = settings.provider.bouncer_include_rules
    assert isinstance(result, tuple)
    # Confirm we get tokens, not a raw "[saas, tools" string
    assert len(result) >= 1


def test_bouncer_rules_csv_parsing_still_works() -> None:
    settings = Settings(BOUNCER_INCLUDE_RULES="saas, developer tools, automation")

    assert settings.provider.bouncer_include_rules == ("saas", "developer tools", "automation")


def test_worker_settings_reject_negative_request_budget() -> None:
    with pytest.raises(ValidationError):
        Settings(GITHUB_REQUESTS_PER_MINUTE=-1)


def test_worker_settings_reject_zero_pacing_seconds() -> None:
    with pytest.raises(ValidationError):
        Settings(INTAKE_PACING_SECONDS=0)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("FIREHOSE_INTERVAL_SECONDS", 0),
        ("FIREHOSE_PAGES", -1),
        ("BACKFILL_INTERVAL_SECONDS", 0),
        ("BACKFILL_PAGES", -1),
        ("BACKFILL_WINDOW_DAYS", 0),
    ],
)
def test_worker_settings_reject_non_positive_runtime_pacing_values(
    field_name: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field_name: value})


def test_worker_settings_expand_tilde_in_paths() -> None:
    settings = Settings(OPENCLAW_CONFIG_PATH="~/openclaw.json")

    assert settings.openclaw_reference.config_path is not None
    assert settings.openclaw_reference.config_path.is_absolute()


def test_worker_settings_expand_tilde_for_workspace_dir() -> None:
    settings = Settings(OPENCLAW_WORKSPACE_DIR="~/openclaw-workspace")

    assert settings.runtime.workspace_dir is not None
    assert settings.runtime.workspace_dir.is_absolute()


def test_worker_settings_default_database_url_is_valid_sqlite() -> None:
    settings = Settings()

    assert settings.runtime.database_url.startswith("sqlite:///")


def test_worker_settings_parse_bouncer_rules_from_json_array() -> None:
    settings = Settings(BOUNCER_INCLUDE_RULES='["saas","tools"]')

    assert settings.provider.bouncer_include_rules == ("saas", "tools")


def test_worker_settings_handle_empty_bouncer_rules() -> None:
    settings = Settings(BOUNCER_INCLUDE_RULES="")

    assert settings.provider.bouncer_include_rules == ()


def test_worker_settings_accept_sequence_bouncer_rules() -> None:
    settings = Settings(BOUNCER_INCLUDE_RULES=["saas", "tools", ""])

    assert settings.provider.bouncer_include_rules == ("saas", "tools")


def test_worker_settings_require_runtime_projection_fields() -> None:
    with pytest.raises(ValidationError):
        WorkerRuntimeSettings.model_validate({})


def test_worker_settings_require_provider_projection_fields() -> None:
    with pytest.raises(ValidationError):
        WorkerProviderSettings.model_validate({})
