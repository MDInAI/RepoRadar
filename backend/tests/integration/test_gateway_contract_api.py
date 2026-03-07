from fastapi.testclient import TestClient
import pytest

from app.api.routes.gateway import get_gateway_contract_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import app
from app.services.openclaw.contract_service import GatewayContractService
from app.services.openclaw.transport import resolve_gateway_target, GatewayTargetResolution

client = TestClient(app)

class FakeAdapter:
    def resolve_transport_target(self) -> GatewayTargetResolution:
        return GatewayTargetResolution(
            configured=False,
            url=None,
            scheme=None,
            token_configured=False,
            allow_insecure_tls=False,
            source="test",
        )

@pytest.fixture(autouse=True)
def _mock_gateway_contract_service():
    app.dependency_overrides[get_gateway_contract_service] = lambda: GatewayContractService(
        adapter=FakeAdapter()
    )
    yield
    app.dependency_overrides.clear()

EXPECTED_ACTIVE_AGENT_KEYS = [
    "overlord",
    "firehose",
    "backfill",
    "bouncer",
    "analyst",
]
EXPECTED_ALL_AGENT_KEYS = [
    *EXPECTED_ACTIVE_AGENT_KEYS,
    "combiner",
    "obsession",
]
EXPECTED_AGENT_ROLES = {
    "overlord": "control-plane-coordinator",
    "firehose": "repository-intake-firehose",
    "backfill": "repository-intake-backfill",
    "bouncer": "repository-triage",
    "analyst": "repository-analysis",
    "combiner": "idea-synthesis",
    "obsession": "idea-tracking",
}


def test_gateway_contract_endpoint_returns_metadata() -> None:
    response = client.get("/api/v1/gateway/contract")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.1.0"
    assert payload["runtime_mode"] == "multi-agent"
    assert payload["frontend_boundary"]["direct_browser_gateway_access"] is False
    assert payload["architecture_flow"] == "frontend -> Agentic-Workflow backend -> Gateway"
    assert [agent["agent_key"] for agent in payload["named_agents"]] == EXPECTED_ALL_AGENT_KEYS
    assert {
        agent["agent_key"]: agent["agent_role"] for agent in payload["named_agents"]
    } == EXPECTED_AGENT_ROLES
    assert any(
        item["name"] == "realtime-events" for item in payload["canonical_interfaces"]
    )


def test_gateway_runtime_endpoint_returns_reserved_shape() -> None:
    response = client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.1.0"
    assert payload["availability"] == "reserved"
    assert payload["runtime"]["runtime_mode"] == "multi-agent"
    assert [agent["agent_key"] for agent in payload["runtime"]["agent_states"]] == EXPECTED_ALL_AGENT_KEYS
    assert payload["runtime"]["agent_states"][0]["agent_role"] == "control-plane-coordinator"
    assert payload["runtime"]["agent_states"][0]["session_affinity"] == {
        "source_of_truth": "gateway",
        "session_id": "reserved-session-overlord",
        "route_key": "agent.overlord",
        "status": "reserved",
    }
    assert payload["runtime"]["agent_states"][-1]["session_affinity"] == {
        "source_of_truth": "gateway",
        "session_id": None,
        "route_key": None,
        "status": "reserved",
    }


def test_gateway_sessions_endpoint_returns_agent_mapped_placeholders() -> None:
    response = client.get("/api/v1/gateway/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.1.0"
    assert payload["availability"] == "reserved"
    assert payload["runtime_mode"] == "multi-agent"
    assert [agent["agent_key"] for agent in payload["named_agents"]] == EXPECTED_ALL_AGENT_KEYS
    assert [session["session_id"] for session in payload["sessions"]] == [
        "reserved-session-overlord",
        "reserved-session-firehose",
        "reserved-session-backfill",
        "reserved-session-bouncer",
        "reserved-session-analyst",
    ]
    assert [session["agent_context"]["agent_key"] for session in payload["sessions"]] == (
        EXPECTED_ACTIVE_AGENT_KEYS
    )
    assert payload["sessions"][0]["agent_context"] == {
        "agent_key": "overlord",
        "display_name": "Overlord",
        "agent_role": "control-plane-coordinator",
    }


def test_gateway_session_detail_endpoint_returns_agent_context_for_reserved_session() -> None:
    response = client.get("/api/v1/gateway/sessions/reserved-session-overlord")

    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "1.1.0",
        "availability": "reserved",
        "source_of_truth": "gateway",
        "session": {
            "session_id": "reserved-session-overlord",
            "label": None,
            "route_key": "agent.overlord",
            "status": "reserved",
            "agent_context": {
                "agent_key": "overlord",
                "display_name": "Overlord",
                "agent_role": "control-plane-coordinator",
            },
            "transcript_available": False,
            "notes": [
                "Story 1.3 reserves agent-aware session detail for later Gateway-backed work.",
            ],
        },
    }


def test_gateway_session_history_endpoint_returns_reserved_shape() -> None:
    response = client.get("/api/v1/gateway/sessions/demo-session/history")

    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "1.1.0",
        "availability": "reserved",
        "source_of_truth": "gateway",
        "session_id": "demo-session",
        "history": [
            {
                "entry_id": "demo-session:placeholder",
                "role": "system",
                "content": None,
                "emitted_at": None,
                "status": "reserved",
            }
        ],
        "notes": [
            "Story 1.2 publishes the normalized history envelope only.",
            "Later stories will replace this placeholder entry with Gateway-backed data.",
        ],
    }


def test_gateway_event_envelope_endpoint_returns_reserved_shape() -> None:
    response = client.get("/api/v1/gateway/events/envelope")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.1.0"
    assert payload["envelope"]["version"] == "v1"
    assert payload["envelope"]["channel"] == "backend-bridge"
    assert [field["name"] for field in payload["envelope"]["fields"]] == [
        "event_id",
        "event_type",
        "session_id",
        "route_key",
        "occurred_at",
        "payload",
    ]


def test_gateway_contract_error_returns_structured_envelope() -> None:
    class BrokenService:
        def get_contract_metadata(self) -> None:
            raise AppError(
                message="Gateway contract lookup failed.",
                code="gateway_contract_lookup_failed",
                status_code=503,
                details={"surface": "gateway-contract"},
            )

    app.dependency_overrides[get_gateway_contract_service] = lambda: BrokenService()
    try:
        response = client.get("/api/v1/gateway/contract")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "gateway_contract_lookup_failed",
            "message": "Gateway contract lookup failed.",
            "details": {"surface": "gateway-contract"},
        }
    }


def test_gateway_contract_endpoint_returns_settings_validation_error_for_invalid_openclaw_config(
    tmp_path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text("{ invalid json", encoding="utf-8")

    class SettingsBackedAdapter:
        def resolve_transport_target(self):
            return resolve_gateway_target(
                Settings(
                    OPENCLAW_CONFIG_PATH=config_path,
                )
            )

    app.dependency_overrides[get_gateway_contract_service] = lambda: GatewayContractService(
        adapter=SettingsBackedAdapter()
    )
    try:
        response = client.get("/api/v1/gateway/contract")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "settings_validation_failed"
    assert payload["error"]["details"]["validation"]["issues"][0]["field"] == "OPENCLAW_CONFIG_PATH"


def test_gateway_sessions_error_returns_structured_envelope() -> None:
    class BrokenService:
        def get_session_surface(self) -> None:
            raise AppError(
                message="Gateway sessions surface failed.",
                code="gateway_sessions_surface_failed",
                status_code=503,
                details={"surface": "gateway-sessions"},
            )

    app.dependency_overrides[get_gateway_contract_service] = lambda: BrokenService()
    try:
        response = client.get("/api/v1/gateway/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "gateway_sessions_surface_failed",
            "message": "Gateway sessions surface failed.",
            "details": {"surface": "gateway-sessions"},
        }
    }
