from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_agent_operator_service
from app.main import app


class _FakeAgentOperatorService:
    def trigger_agent_run(self, agent_name: str):
        return {
            "agent_name": agent_name,
            "accepted": True,
            "trigger_mode": "background-subprocess",
            "triggered_at": datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            "message": f"Manual {agent_name} run launched in the worker runtime.",
        }

def test_trigger_agent_run_returns_accepted_response() -> None:
    with TestClient(app) as test_client:
        app.dependency_overrides[get_agent_operator_service] = lambda: _FakeAgentOperatorService()
        try:
            response = test_client.post("/api/v1/agents/firehose/run")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 202
    data = response.json()
    assert data["agent_name"] == "firehose"
    assert data["accepted"] is True
    assert data["trigger_mode"] == "background-subprocess"
