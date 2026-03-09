from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import get_settings_service
from app.core.config import Settings
from app.main import app
from app.services.settings_service import SettingsService


def test_settings_summary_endpoint_returns_backend_owned_masked_state(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {
                    "url": "wss://gateway.local",
                    "auth": {"token": "gateway-token"},
                    "allowInsecureTls": False,
                },
                "agents": {"defaults": {"model": "openai/gpt-5-mini"}},
                "channels": {"telegram": {"enabled": True}},
            }
        ),
        encoding="utf-8",
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
            AGENTIC_RUNTIME_DIR=tmp_path / "runtime",
            GITHUB_PROVIDER_TOKEN="github-provider-token",
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.0.0"
    assert payload["validation"]["valid"] is True
    assert payload["worker_settings"]
    assert any(item["owner"] == "gateway" for item in payload["ownership"])
    assert any(item["key"] == "gateway.auth.token" for item in payload["openclaw_settings"])
    assert payload["openclaw_settings"][1]["value"] == "configured"


def test_settings_summary_endpoint_accepts_json5_and_object_model_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        """
        {
          gateway: {
            auth: { token: "gateway-token" },
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
        encoding="utf-8",
    )

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
            AGENTIC_RUNTIME_DIR=tmp_path / "runtime",
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    default_model = next(
        item for item in payload["openclaw_settings"] if item["key"] == "agents.defaults.model"
    )
    assert default_model["value"] == "openai/gpt-5-mini"


def test_settings_summary_endpoint_returns_structured_422_for_missing_config(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=tmp_path / "missing-openclaw.json",
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "settings_validation_failed",
            "message": "Configuration validation failed.",
            "details": {
                "validation": {
                    "valid": False,
                    "issues": [
                        {
                            "severity": "error",
                            "field": "OPENCLAW_CONFIG_PATH",
                            "owner": "openclaw",
                            "code": "openclaw_config_missing",
                            "message": "OpenClaw config file was not found.",
                            "source": "openclaw-config",
                        }
                    ],
                }
            },
        }
    }


def test_settings_summary_endpoint_returns_structured_422_for_invalid_workspace_dir(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"url": "wss://gateway.local", "auth": {"token": "gateway-token"}},
                "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
            }
        ),
        encoding="utf-8",
    )

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=tmp_path / "missing-workspace",
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    issues = response.json()["error"]["details"]["validation"]["issues"]
    assert any(
        issue["field"] == "OPENCLAW_WORKSPACE_DIR" and issue["code"] == "workspace_dir_invalid"
        for issue in issues
    )


def test_settings_summary_endpoint_returns_422_for_blank_runtime_dir(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"url": "wss://gateway.local", "auth": {"token": "gateway-token"}},
                "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
            }
        ),
        encoding="utf-8",
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
            AGENTIC_RUNTIME_DIR="   ",
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    issues = response.json()["error"]["details"]["validation"]["issues"]
    assert any(
        issue["field"] == "AGENTIC_RUNTIME_DIR" and issue["code"] == "runtime_dir_missing"
        for issue in issues
    )


def test_settings_summary_endpoint_returns_422_for_invalid_gateway_port(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {
                    "url": "wss://gateway.local:invalid-port",
                    "auth": {"token": "gateway-token"},
                },
                "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
            }
        ),
        encoding="utf-8",
    )
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
        )
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "gateway_url_port_invalid"


def test_settings_summary_endpoint_surfaces_worker_drift_warnings(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"url": "wss://gateway.local", "auth": {"token": "gateway-token"}},
                "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
            }
        ),
        encoding="utf-8",
    )
    backend_workspace = tmp_path / "workspace-backend"
    backend_workspace.mkdir()
    worker_workspace = tmp_path / "workspace-worker"
    worker_workspace.mkdir()
    worker_dir = tmp_path / "workers"
    worker_dir.mkdir()
    (worker_dir / ".env").write_text(
        "\n".join(
            [
                f"OPENCLAW_WORKSPACE_DIR={worker_workspace}",
                "GITHUB_PROVIDER_TOKEN=worker-provider-token",
                "GITHUB_REQUESTS_PER_MINUTE=25",
                "INTAKE_PACING_SECONDS=15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=backend_workspace,
        ),
        project_root=tmp_path,
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert any(
        issue["code"] == "worker_workspace_dir_differs" for issue in payload["validation"]["issues"]
    )
    assert any(
        issue["code"] == "worker_github_provider_token_differs"
        for issue in payload["validation"]["issues"]
    )
    assert any(
        issue["code"] == "worker_github_requests_per_minute_differs"
        for issue in payload["validation"]["issues"]
    )
    assert any(
        issue["code"] == "worker_intake_pacing_seconds_differs"
        for issue in payload["validation"]["issues"]
    )
    assert any(
        item["key"] == "workers.OPENCLAW_WORKSPACE_DIR" and item["source"] == "workers-env"
        for item in payload["worker_settings"]
    )


def test_settings_summary_endpoint_prefers_process_env_over_worker_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {"url": "wss://gateway.local", "auth": {"token": "gateway-token"}},
                "agents": {"defaults": {"model": {"primary": "openai/gpt-5-mini"}}},
            }
        ),
        encoding="utf-8",
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

    app.dependency_overrides[get_settings_service] = lambda: SettingsService(
        app_settings=Settings(
            OPENCLAW_CONFIG_PATH=config_path,
            OPENCLAW_WORKSPACE_DIR=workspace_dir,
            GITHUB_PROVIDER_TOKEN="shared-provider-token",
            GITHUB_REQUESTS_PER_MINUTE=60,
            INTAKE_PACING_SECONDS=30,
        ),
        project_root=tmp_path,
    )
    try:
        client = TestClient(app)
        response = client.get("/api/v1/settings/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["issues"] == []
    assert all(item["source"] == "shared-project-env" for item in payload["worker_settings"])
    assert any(
        item["key"] == "workers.GITHUB_REQUESTS_PER_MINUTE" and item["value"] == "60"
        for item in payload["worker_settings"]
    )
    assert any(
        item["key"] == "workers.INTAKE_PACING_SECONDS" and item["value"] == "30"
        for item in payload["worker_settings"]
    )
