from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.openclaw.contract_service import GatewayContractService
from app.services.openclaw.transport import (
    GatewayTargetResolution,
    map_gateway_transport_error,
    normalize_gateway_url,
    resolve_gateway_target,
)


EXPECTED_AGENT_KEYS = [
    "overlord",
    "firehose",
    "backfill",
    "bouncer",
    "analyst",
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
EXPECTED_ACTIVE_SESSION_IDS = [
    "reserved-session-overlord",
    "reserved-session-firehose",
    "reserved-session-backfill",
    "reserved-session-bouncer",
    "reserved-session-analyst",
]


class FakeAdapter:
    def __init__(self, resolution: GatewayTargetResolution) -> None:
        self.resolution = resolution

    def resolve_transport_target(self) -> GatewayTargetResolution:
        return self.resolution


class ExplodingAdapter:
    def resolve_transport_target(self) -> GatewayTargetResolution:
        raise RuntimeError("socket closed")


def test_normalize_gateway_url_adds_default_port_and_trims_trailing_slash() -> None:
    assert normalize_gateway_url("ws://localhost/") == "ws://localhost:18789"


def test_normalize_gateway_url_rejects_invalid_scheme() -> None:
    with pytest.raises(AppError) as exc_info:
        normalize_gateway_url("http://localhost:18789")

    assert exc_info.value.code == "gateway_url_scheme_invalid"
    assert exc_info.value.status_code == 422


def test_normalize_gateway_url_rejects_missing_host_with_validation_status() -> None:
    with pytest.raises(AppError) as exc_info:
        normalize_gateway_url("ws:///gateway")

    assert exc_info.value.code == "gateway_url_host_missing"
    assert exc_info.value.status_code == 422


def test_normalize_gateway_url_rejects_invalid_port_with_validation_status() -> None:
    with pytest.raises(AppError) as exc_info:
        normalize_gateway_url("ws://localhost:invalid-port")

    assert exc_info.value.code == "gateway_url_port_invalid"
    assert exc_info.value.status_code == 422


def test_resolve_gateway_target_reads_openclaw_config_reference(tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {
                    "remote": {
                        "url": "wss://gateway.local",
                        "allowInsecureTls": True,
                    },
                    "auth": {"token": "gateway-token"},
                },
                "agents": {
                    "defaults": {
                        "model": {"primary": "test-model"}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    resolution = resolve_gateway_target(
        Settings(
            OPENCLAW_CONFIG_PATH=config_path,
        )
    )

    assert resolution.configured is True
    assert resolution.url == "wss://gateway.local:18789"
    assert resolution.token_configured is True
    assert resolution.allow_insecure_tls is True
    assert resolution.source == "openclaw-config"


def test_resolve_gateway_target_raises_settings_validation_error_for_invalid_openclaw_config(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        resolve_gateway_target(
            Settings(
                OPENCLAW_CONFIG_PATH=config_path,
            )
        )

    assert exc_info.value.code == "settings_validation_failed"
    assert exc_info.value.status_code == 422
    assert exc_info.value.details["validation"]["issues"][0]["field"] == "OPENCLAW_CONFIG_PATH"


def test_gateway_contract_service_uses_adapter_resolution() -> None:
    service = GatewayContractService(
        adapter=FakeAdapter(
            GatewayTargetResolution(
                configured=True,
                url="wss://gateway.local:9443",
                scheme="wss",
                token_configured=True,
                allow_insecure_tls=True,
                source="settings",
                notes=("Configured in test.",),
            )
        )
    )

    response = service.get_contract_metadata()

    assert response.transport_target.url == "wss://gateway.local:9443"
    assert response.transport_target.allow_insecure_tls is True
    assert response.frontend_boundary.direct_browser_gateway_access is False
    assert response.runtime_mode == "multi-agent"
    assert [agent.agent_key for agent in response.named_agents] == EXPECTED_AGENT_KEYS
    assert response.named_agents[0].agent_role == "control-plane-coordinator"
    assert response.named_agents[0].agent_role != response.named_agents[0].agent_key


def test_gateway_contract_service_returns_reserved_session_shape() -> None:
    service = GatewayContractService(
        adapter=FakeAdapter(
            GatewayTargetResolution(
                configured=False,
                url=None,
                scheme=None,
                token_configured=False,
                allow_insecure_tls=False,
                source="settings-placeholder",
            )
        )
    )

    response = service.get_session_surface()

    assert response.availability == "reserved"
    assert response.runtime_mode == "multi-agent"
    assert response.source_of_truth == "gateway"
    assert [agent.agent_key for agent in response.named_agents] == EXPECTED_AGENT_KEYS
    assert [session.session_id for session in response.sessions] == EXPECTED_ACTIVE_SESSION_IDS
    assert response.sessions[0].agent_context is not None
    assert response.sessions[0].agent_context.agent_key == "overlord"
    assert response.sessions[0].agent_context.agent_role == "control-plane-coordinator"


def test_gateway_contract_service_returns_multi_agent_runtime_placeholders() -> None:
    service = GatewayContractService(
        adapter=FakeAdapter(
            GatewayTargetResolution(
                configured=False,
                url=None,
                scheme=None,
                token_configured=False,
                allow_insecure_tls=False,
                source="settings-placeholder",
            )
        )
    )

    response = service.get_runtime_surface()

    assert response.contract_version == "1.1.0"
    assert response.runtime.runtime_mode == "multi-agent"
    assert [agent.agent_key for agent in response.runtime.agent_states] == EXPECTED_AGENT_KEYS
    assert response.runtime.agent_states[0].agent_role == "control-plane-coordinator"
    assert response.runtime.agent_states[0].session_affinity.session_id == "reserved-session-overlord"
    assert response.runtime.agent_states[0].session_affinity.route_key == "agent.overlord"
    assert response.runtime.agent_states[-1].session_affinity.session_id is None
    assert response.runtime.agent_states[0].queue.status == "reserved"
    assert response.runtime.agent_states[0].monitoring.status == "reserved"


def test_gateway_contract_service_returns_agent_context_for_reserved_session_detail() -> None:
    service = GatewayContractService(
        adapter=FakeAdapter(
            GatewayTargetResolution(
                configured=False,
                url=None,
                scheme=None,
                token_configured=False,
                allow_insecure_tls=False,
                source="settings-placeholder",
            )
        )
    )

    response = service.get_session_detail_surface("reserved-session-overlord")

    assert response.session.route_key == "agent.overlord"
    assert response.session.agent_context is not None
    assert response.session.agent_context.agent_key == "overlord"
    assert response.session.agent_context.agent_role == "control-plane-coordinator"


def test_gateway_contract_service_wraps_adapter_errors() -> None:
    service = GatewayContractService(adapter=ExplodingAdapter())

    with pytest.raises(AppError) as exc_info:
        service.get_runtime_surface()

    assert exc_info.value.code == "gateway_transport_unavailable"
    assert exc_info.value.status_code == 502


def test_map_gateway_transport_error_preserves_reason() -> None:
    error = map_gateway_transport_error("gateway handshake timed out")

    assert error.code == "gateway_transport_unavailable"
    assert error.details == {"reason": "gateway handshake timed out"}


def test_agent_role_map_remains_distinct_from_agent_keys() -> None:
    service = GatewayContractService(
        adapter=FakeAdapter(
            GatewayTargetResolution(
                configured=False,
                url=None,
                scheme=None,
                token_configured=False,
                allow_insecure_tls=False,
                source="settings-placeholder",
            )
        )
    )

    named_agents = service.get_contract_metadata().named_agents

    assert {agent.agent_key: agent.agent_role for agent in named_agents} == EXPECTED_AGENT_ROLES
