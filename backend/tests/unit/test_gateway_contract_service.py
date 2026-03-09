from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.core.config import Settings
from app.core.errors import AppError
from app.models import (
    BackfillProgress,
    FirehoseProgress,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
)
from app.repositories.intake_runtime_repository import IntakeRuntimeRepository
from app.services.openclaw.contract_service import GatewayContractService
from app.services.intake_runtime_service import GatewayIntakeRuntimeService
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

    assert response.contract_version == "1.2.0"
    assert response.runtime.runtime_mode == "multi-agent"
    assert [agent.agent_key for agent in response.runtime.agent_states] == EXPECTED_AGENT_KEYS
    assert response.runtime.agent_states[0].agent_role == "control-plane-coordinator"
    assert response.runtime.agent_states[0].session_affinity.session_id == "reserved-session-overlord"
    assert response.runtime.agent_states[0].session_affinity.route_key == "agent.overlord"
    assert response.runtime.agent_states[-1].session_affinity.session_id is None
    assert response.runtime.agent_states[0].queue.status == "reserved"
    assert response.runtime.agent_states[0].monitoring.status == "reserved"


def test_gateway_contract_service_returns_live_intake_runtime_surface(
    tmp_path: Path,
) -> None:
    with _runtime_session() as session:
        _seed_runtime_state(session)
        (tmp_path / "firehose").mkdir()
        (tmp_path / "backfill").mkdir()
        (tmp_path / "firehose" / "progress.json").write_text(
            json.dumps({"generated_at": "2026-03-07T10:16:00+00:00"}),
            encoding="utf-8",
        )
        (tmp_path / "backfill" / "progress.json").write_text(
            json.dumps({"generated_at": "2026-03-07T09:45:00+00:00"}),
            encoding="utf-8",
        )

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
            ),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    assert response.contract_version == "1.2.0"
    assert response.availability == "available"
    assert response.runtime.source_of_truth == "agentic-workflow+gateway"

    firehose = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "firehose"
    )
    assert firehose.queue.status == "live"
    assert firehose.queue.state_counts.model_dump() == {
        "pending": 1,
        "in_progress": 1,
        "completed": 0,
        "failed": 1,
    }
    assert firehose.queue.total_items == 3
    assert firehose.queue.checkpoint.kind == "firehose"
    assert firehose.queue.checkpoint.active_mode == "trending"
    assert firehose.queue.checkpoint.next_page == 4
    assert firehose.queue.checkpoint.resume_required is True
    assert firehose.queue.checkpoint.new_anchor_date == date(2026, 3, 5)
    assert firehose.queue.checkpoint.trending_anchor_date == date(2026, 2, 28)
    assert firehose.queue.checkpoint.mirror_snapshot_generated_at == datetime(
        2026, 3, 7, 10, 16, tzinfo=timezone.utc
    )

    backfill = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "backfill"
    )
    assert backfill.queue.status == "live"
    assert backfill.queue.state_counts.model_dump() == {
        "pending": 0,
        "in_progress": 1,
        "completed": 1,
        "failed": 0,
    }
    assert backfill.queue.total_items == 2
    assert backfill.queue.checkpoint.kind == "backfill"
    assert backfill.queue.checkpoint.window_start_date == date(2025, 1, 1)
    assert backfill.queue.checkpoint.created_before_boundary == date(2025, 1, 31)
    assert backfill.queue.checkpoint.created_before_cursor == datetime(
        2025, 1, 15, 12, 0, tzinfo=timezone.utc
    )
    assert backfill.queue.checkpoint.next_page == 3
    assert backfill.queue.checkpoint.exhausted is False

    bouncer = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "bouncer"
    )
    assert bouncer.queue.status == "reserved"


def test_gateway_contract_service_returns_zero_value_buckets_for_empty_intake_state(
    tmp_path: Path,
) -> None:
    with _runtime_session() as session:
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
            ),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    firehose = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "firehose"
    )
    assert firehose.queue.status == "live"
    assert firehose.queue.state_counts.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert firehose.queue.total_items == 0
    assert firehose.queue.checkpoint.kind == "firehose"
    assert firehose.queue.checkpoint.next_page == 1
    assert firehose.queue.checkpoint.resume_required is None
    assert firehose.queue.checkpoint.last_checkpointed_at is None

    backfill = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "backfill"
    )
    assert backfill.queue.status == "live"
    assert backfill.queue.state_counts.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert backfill.queue.checkpoint.kind == "backfill"
    assert backfill.queue.checkpoint.window_start_date is None
    assert backfill.queue.checkpoint.exhausted is None


def test_gateway_contract_service_returns_runtime_surface_for_invalid_gateway_url(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        json.dumps(
            {
                "gateway": {
                    "remote": {
                        "url": "http://bad-host",
                        "allowInsecureTls": False,
                    },
                    "auth": {"token": "gateway-token"},
                },
                "agents": {
                    "defaults": {
                        "model": {"primary": "test-model"}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    class SettingsBackedAdapter:
        def resolve_transport_target(self):
            return resolve_gateway_target(
                Settings(
                    OPENCLAW_CONFIG_PATH=config_path,
                )
            )

    with _runtime_session() as session:
        service = GatewayContractService(
            adapter=SettingsBackedAdapter(),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    assert response.availability == "available"
    assert response.runtime.gateway_url is None
    firehose = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "firehose"
    )
    assert firehose.queue.status == "live"


def test_gateway_contract_service_handles_partial_firehose_progress_without_queue_rows(
    tmp_path: Path,
) -> None:
    with _runtime_session() as session:
        session.add(
            FirehoseProgress(
                source_provider="github",
                active_mode=None,
                next_page=2,
                new_anchor_date=None,
                trending_anchor_date=None,
                run_started_at=None,
                resume_required=False,
                last_checkpointed_at=None,
                updated_at=datetime(2026, 3, 7, 11, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

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
            ),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    firehose = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "firehose"
    )
    assert firehose.queue.status == "live"
    assert firehose.queue.state_counts.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert firehose.queue.total_items == 0
    assert firehose.queue.checkpoint.kind == "firehose"
    assert firehose.queue.checkpoint.active_mode is None
    assert firehose.queue.checkpoint.next_page == 2
    assert firehose.queue.checkpoint.resume_required is False
    assert firehose.queue.checkpoint.new_anchor_date is None
    assert firehose.queue.checkpoint.trending_anchor_date is None
    assert firehose.queue.checkpoint.run_started_at is None
    assert firehose.queue.checkpoint.last_checkpointed_at is None


def test_gateway_contract_service_handles_backfill_checkpoint_without_queue_rows(
    tmp_path: Path,
) -> None:
    with _runtime_session() as session:
        session.add(
            BackfillProgress(
                source_provider="github",
                window_start_date=date(2025, 2, 1),
                created_before_boundary=date(2025, 2, 28),
                created_before_cursor=None,
                next_page=4,
                exhausted=False,
                last_checkpointed_at=None,
                updated_at=datetime(2026, 3, 7, 8, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

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
            ),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    backfill = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "backfill"
    )
    assert backfill.queue.status == "live"
    assert backfill.queue.state_counts.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert backfill.queue.total_items == 0
    assert backfill.queue.checkpoint.kind == "backfill"
    assert backfill.queue.checkpoint.window_start_date == date(2025, 2, 1)
    assert backfill.queue.checkpoint.created_before_boundary == date(2025, 2, 28)
    assert backfill.queue.checkpoint.created_before_cursor is None
    assert backfill.queue.checkpoint.next_page == 4
    assert backfill.queue.checkpoint.exhausted is False
    assert backfill.queue.checkpoint.last_checkpointed_at is None


def test_gateway_contract_service_surfaces_snapshot_issue_notes(
    tmp_path: Path,
) -> None:
    with _runtime_session() as session:
        firehose_dir = tmp_path / "firehose"
        firehose_dir.mkdir()
        (firehose_dir / "progress.json").write_text("{ invalid json", encoding="utf-8")

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
            ),
            intake_runtime_service=GatewayIntakeRuntimeService(
                IntakeRuntimeRepository(session, runtime_dir=tmp_path)
            ),
        )

        response = service.get_runtime_surface()

    firehose = next(
        agent for agent in response.runtime.agent_states if agent.agent_key == "firehose"
    )
    assert (
        "The runtime/firehose/progress.json mirror snapshot is currently invalid."
        in firehose.queue.notes
    )


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


@contextmanager
def _runtime_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_runtime_state(session: Session) -> None:
    now = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            RepositoryIntake(
                github_repository_id=1,
                owner_login="octocat",
                repository_name="firehose-pending",
                full_name="octocat/firehose-pending",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.PENDING,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=2,
                owner_login="octocat",
                repository_name="firehose-running",
                full_name="octocat/firehose-running",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.IN_PROGRESS,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=3,
                owner_login="octocat",
                repository_name="firehose-failed",
                full_name="octocat/firehose-failed",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.FAILED,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=4,
                owner_login="octocat",
                repository_name="backfill-complete",
                full_name="octocat/backfill-complete",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=5,
                owner_login="octocat",
                repository_name="backfill-running",
                full_name="octocat/backfill-running",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.IN_PROGRESS,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
        ]
    )
    session.add(
        FirehoseProgress(
            source_provider="github",
            active_mode=RepositoryFirehoseMode.TRENDING,
            next_page=4,
            new_anchor_date=date(2026, 3, 5),
            trending_anchor_date=date(2026, 2, 28),
            run_started_at=datetime(2026, 3, 7, 9, 0, tzinfo=timezone.utc),
            resume_required=True,
            last_checkpointed_at=datetime(2026, 3, 7, 10, 15, tzinfo=timezone.utc),
            updated_at=now,
        )
    )
    session.add(
        BackfillProgress(
            source_provider="github",
            window_start_date=date(2025, 1, 1),
            created_before_boundary=date(2025, 1, 31),
            created_before_cursor=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
            next_page=3,
            exhausted=False,
            last_checkpointed_at=datetime(2026, 3, 7, 9, 45, tzinfo=timezone.utc),
            updated_at=now,
        )
    )
    session.commit()
