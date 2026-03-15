from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_agent_config_service
from app.main import app


class _FakeAgentConfigService:
    def get_agent_config(self, agent_name: str):
        return {
            "agent_name": agent_name,
            "display_name": "Firehose",
            "editable": True,
            "summary": "Control Firehose",
            "apply_notes": ["Restart scheduler loop for auto cadence changes."],
            "fields": [
                {
                    "key": "FIREHOSE_INTERVAL_SECONDS",
                    "label": "Interval",
                    "description": "How long Firehose waits between runs.",
                    "input_kind": "integer",
                    "value": "3600",
                    "unit": "seconds",
                    "min_value": 1,
                    "placeholder": None,
                }
            ],
        }

    def update_agent_config(self, agent_name: str, request):
        payload = self.get_agent_config(agent_name)
        payload["message"] = f"Saved {agent_name}"
        payload["fields"][0]["value"] = request.values.get("FIREHOSE_INTERVAL_SECONDS", "3600")
        return payload


def test_get_agent_config_returns_editable_fields() -> None:
    with TestClient(app) as test_client:
        app.dependency_overrides[get_agent_config_service] = lambda: _FakeAgentConfigService()
        try:
            response = test_client.get("/api/v1/agents/firehose/config")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "firehose"
    assert data["editable"] is True
    assert data["fields"][0]["key"] == "FIREHOSE_INTERVAL_SECONDS"


def test_patch_agent_config_returns_saved_values() -> None:
    with TestClient(app) as test_client:
        app.dependency_overrides[get_agent_config_service] = lambda: _FakeAgentConfigService()
        try:
            response = test_client.patch(
                "/api/v1/agents/firehose/config",
                json={"values": {"FIREHOSE_INTERVAL_SECONDS": "900"}},
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Saved firehose"
    assert data["fields"][0]["value"] == "900"
