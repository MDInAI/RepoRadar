from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.settings_service import SettingsService


def _write_openclaw_config(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_openclaw_config_text(path: Path, payload: str) -> Path:
    path.write_text(payload, encoding="utf-8")
    return path


def test_settings_service_returns_masked_configuration_summary(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
                "allowInsecureTls": False,
            },
            "agents": {"defaults": {"model": "openai/gpt-5-mini"}},
            "channels": {"telegram": {"enabled": True}},
        },
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    app_settings = Settings(
        DATABASE_URL="sqlite:///../runtime/data/sqlite/agentic_workflow.db",
        SECRET_KEY="backend-secret-key",
        OPENCLAW_CONFIG_PATH=config_path,
        OPENCLAW_WORKSPACE_DIR=workspace_dir,
        AGENTIC_RUNTIME_DIR=tmp_path / "runtime",
        GITHUB_PROVIDER_TOKEN="github-provider-token",
        GITHUB_REQUESTS_PER_MINUTE=45,
        INTAKE_PACING_SECONDS=20,
    )

    response = SettingsService(app_settings=app_settings).get_settings_summary()

    assert response.contract_version == "1.0.0"
    assert response.validation.valid is True
    assert response.worker_settings
    assert {entry.owner for entry in response.ownership} == {
        "agentic-workflow",
        "gateway",
        "openclaw",
        "workspace",
    }

    gateway_url = next(item for item in response.openclaw_settings if item.key == "gateway.url")
    gateway_token = next(
        item for item in response.openclaw_settings if item.key == "gateway.auth.token"
    )
    provider_token = next(
        item for item in response.project_settings if item.key == "GITHUB_PROVIDER_TOKEN"
    )

    assert gateway_url.value == "wss://gateway.local:18789"
    assert gateway_token.value == "configured"
    assert gateway_token.secret is True
    assert provider_token.value == "configured"
    assert provider_token.secret is True
    assert all(item.source == "shared-project-env" for item in response.worker_settings)


def test_settings_service_accepts_json5_style_openclaw_config(tmp_path: Path) -> None:
    config_path = _write_openclaw_config_text(
        tmp_path / "openclaw.json",
        """
        {
          // Local OpenClaw config comments are valid JSON5
          gateway: {
            auth: { token: "gateway-token-value" },
            remote: {
              url: "wss://gateway.local",
              allowInsecureTls: false,
            },
          },
          agents: {
            defaults: {
              model: {
                primary: "openai/gpt-5-mini",
                fallbacks: ["openai/gpt-5-nano"],
              },
            },
          },
          channels: {
            telegram: { enabled: true },
          },
        }
        """,
    )
    app_settings = Settings(
        OPENCLAW_CONFIG_PATH=config_path,
        OPENCLAW_WORKSPACE_DIR=(tmp_path / "workspace"),
        AGENTIC_RUNTIME_DIR=tmp_path / "runtime",
    )
    assert app_settings.OPENCLAW_WORKSPACE_DIR is not None
    app_settings.OPENCLAW_WORKSPACE_DIR.mkdir()

    response = SettingsService(app_settings=app_settings).get_settings_summary()

    default_model = next(
        item for item in response.openclaw_settings if item.key == "agents.defaults.model"
    )
    assert default_model.value == "openai/gpt-5-mini"
    assert default_model.configured is True


def test_settings_service_raises_validation_error_for_missing_openclaw_config(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    app_settings = Settings(
        OPENCLAW_CONFIG_PATH=tmp_path / "missing-openclaw.json",
        OPENCLAW_WORKSPACE_DIR=workspace_dir,
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(app_settings=app_settings).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert exc_info.value.status_code == 422
    assert exc_info.value.details["validation"]["valid"] is False
    assert exc_info.value.details["validation"]["issues"][0]["field"] == "OPENCLAW_CONFIG_PATH"


def test_settings_service_reuses_gateway_url_validation_for_openclaw_config(
    tmp_path: Path,
) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "http://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": "openai/gpt-5-mini"}},
        },
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    app_settings = Settings(
        OPENCLAW_CONFIG_PATH=config_path,
        OPENCLAW_WORKSPACE_DIR=workspace_dir,
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(app_settings=app_settings).get_settings_summary()

    assert exc_info.value.code == "gateway_url_scheme_invalid"
    assert exc_info.value.status_code == 422


def test_settings_service_rejects_blank_project_owned_runtime_settings(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                DATABASE_URL="   ",
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=workspace_dir,
            )
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert exc_info.value.status_code == 422
    assert any(
        issue["field"] == "DATABASE_URL"
        for issue in exc_info.value.details["validation"]["issues"]
    )


def test_settings_service_rejects_blank_project_runtime_dir(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=workspace_dir,
                AGENTIC_RUNTIME_DIR="   ",
            )
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert any(
        issue["field"] == "AGENTIC_RUNTIME_DIR"
        and issue["code"] == "runtime_dir_missing"
        for issue in exc_info.value.details["validation"]["issues"]
    )


def test_settings_service_rejects_missing_workspace_dir(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=None,
            )
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert any(
        issue["field"] == "OPENCLAW_WORKSPACE_DIR"
        and issue["code"] == "workspace_dir_missing"
        for issue in exc_info.value.details["validation"]["issues"]
    )


def test_settings_service_rejects_nonexistent_workspace_dir(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=tmp_path / "missing-workspace",
            )
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert any(
        issue["field"] == "OPENCLAW_WORKSPACE_DIR"
        and issue["code"] == "workspace_dir_invalid"
        for issue in exc_info.value.details["validation"]["issues"]
    )


def test_settings_service_surfaces_worker_drift_warnings(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    backend_workspace = tmp_path / "workspace-backend"
    backend_workspace.mkdir()
    worker_workspace = tmp_path / "workspace-worker"
    worker_workspace.mkdir()
    worker_env_dir = tmp_path / "workers"
    worker_env_dir.mkdir()
    (worker_env_dir / ".env").write_text(
        "\n".join(
            [
                "DATABASE_URL=sqlite:///../runtime/data/sqlite/worker.db",
                f"OPENCLAW_WORKSPACE_DIR={worker_workspace}",
                "GITHUB_PROVIDER_TOKEN=worker-provider-token",
                "GITHUB_REQUESTS_PER_MINUTE=25",
                "INTAKE_PACING_SECONDS=15",
            ]
        ),
        encoding="utf-8",
    )

    response = SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=backend_workspace,
        ),
        project_root=tmp_path,
    ).get_settings_summary()

    assert response.validation.valid is True
    assert any(
        issue.code == "worker_workspace_dir_differs" for issue in response.validation.issues
    )
    assert any(
        issue.code == "worker_github_provider_token_differs"
        for issue in response.validation.issues
    )
    assert any(
        issue.code == "worker_github_requests_per_minute_differs"
        for issue in response.validation.issues
    )
    assert any(
        issue.code == "worker_intake_pacing_seconds_differs"
        for issue in response.validation.issues
    )
    assert any(
        item.key == "workers.OPENCLAW_WORKSPACE_DIR"
        and item.source == "workers-env"
        and item.value == str(worker_workspace)
        for item in response.worker_settings
    )


def test_settings_service_uses_process_env_precedence_for_worker_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    worker_env_dir = tmp_path / "workers"
    worker_env_dir.mkdir()
    (worker_env_dir / ".env").write_text(
        "\n".join(
            [
                f"OPENCLAW_WORKSPACE_DIR={tmp_path / 'unused-worker-workspace'}",
                "GITHUB_PROVIDER_TOKEN=worker-provider-token",
                "GITHUB_REQUESTS_PER_MINUTE=25",
                "INTAKE_PACING_SECONDS=15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setenv("GITHUB_PROVIDER_TOKEN", "shared-provider-token")
    monkeypatch.setenv("GITHUB_REQUESTS_PER_MINUTE", "60")
    monkeypatch.setenv("INTAKE_PACING_SECONDS", "30")

    response = SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
            GITHUB_PROVIDER_TOKEN="shared-provider-token",
            GITHUB_REQUESTS_PER_MINUTE=60,
            INTAKE_PACING_SECONDS=30,
        ),
        project_root=tmp_path,
    ).get_settings_summary()

    assert response.validation.valid is True
    assert response.validation.issues == []
    assert all(item.source == "shared-project-env" for item in response.worker_settings)
    assert any(
        item.key == "workers.GITHUB_REQUESTS_PER_MINUTE" and item.value == "60"
        for item in response.worker_settings
    )
    assert any(
        item.key == "workers.INTAKE_PACING_SECONDS" and item.value == "30"
        for item in response.worker_settings
    )


def test_settings_service_rejects_invalid_gateway_port_from_openclaw_config(
    tmp_path: Path,
) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local:invalid-port",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    app_settings = Settings(
        OPENCLAW_CONFIG_PATH=config_path,
        OPENCLAW_WORKSPACE_DIR=workspace_dir,
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(app_settings=app_settings).get_settings_summary()

    assert exc_info.value.code == "gateway_url_port_invalid"
    assert exc_info.value.status_code == 422


def test_settings_service_rejects_invalid_worker_workspace_dir(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    backend_workspace = tmp_path / "workspace-backend"
    backend_workspace.mkdir()
    worker_env_dir = tmp_path / "workers"
    worker_env_dir.mkdir()
    (worker_env_dir / ".env").write_text(
        f"OPENCLAW_WORKSPACE_DIR={tmp_path / 'missing-worker-workspace'}\n",
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=backend_workspace,
            ),
            project_root=tmp_path,
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert any(
        issue["field"] == "workers.OPENCLAW_WORKSPACE_DIR"
        and issue["code"] == "worker_workspace_dir_invalid"
        for issue in exc_info.value.details["validation"]["issues"]
    )


def test_settings_service_accepts_dotenv_inline_comments(tmp_path: Path) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {
            "gateway": {
                "url": "wss://gateway.local",
                "auth": {"token": "gateway-token-value"},
            },
            "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
        },
    )
    backend_workspace = tmp_path / "workspace-backend"
    backend_workspace.mkdir()
    worker_workspace = tmp_path / "workspace-worker"
    worker_workspace.mkdir()
    worker_env_dir = tmp_path / "workers"
    worker_env_dir.mkdir()
    (worker_env_dir / ".env").write_text(
        "DATABASE_URL=sqlite:///../runtime/data/sqlite/worker.db # inline comment\n"
        f"OPENCLAW_WORKSPACE_DIR='{worker_workspace}' # with quotes\n"
        'GITHUB_PROVIDER_TOKEN="worker-provider-token"\n'
        "GITHUB_REQUESTS_PER_MINUTE=25\n"
        "INTAKE_PACING_SECONDS=15\n",
        encoding="utf-8",
    )

    response = SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=backend_workspace,
        ),
        project_root=tmp_path,
    ).get_settings_summary()

    assert response.validation.valid is True
    assert any(
        item.key == "workers.DATABASE_URL" and item.value == "sqlite:///../runtime/data/sqlite/worker.db"
        for item in response.worker_settings
    )
    assert any(
        item.key == "workers.OPENCLAW_WORKSPACE_DIR" and item.value == str(worker_workspace)
        for item in response.worker_settings
    )


def test_settings_service_raises_validation_error_for_unreadable_openclaw_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_openclaw_config(
        tmp_path / "openclaw.json",
        {"gateway": {"url": "wss://test", "auth": {"token": "test"}}, "agents": {"defaults": {"model": "test"}}},
    )
    def mock_read_text(*args, **kwargs):
        raise PermissionError("Permission denied")
    monkeypatch.setattr(Path, "read_text", mock_read_text)
    
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    with pytest.raises(AppError) as exc_info:
        SettingsService(
            app_settings=Settings(
                OPENCLAW_CONFIG_PATH=config_path,
                OPENCLAW_WORKSPACE_DIR=workspace_dir,
            )
        ).get_settings_summary()

    assert exc_info.value.code == "settings_validation_failed"
    assert exc_info.value.details["validation"]["issues"][0]["code"] == "openclaw_config_unreadable"
