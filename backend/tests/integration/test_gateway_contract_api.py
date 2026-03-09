from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.api.routes.gateway import get_gateway_contract_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import app
from app.models import (
    BackfillProgress,
    FirehoseProgress,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
)
from app.repositories.intake_runtime_repository import IntakeRuntimeRepository
from app.services.intake_runtime_service import GatewayIntakeRuntimeService
from app.services.openclaw.contract_service import GatewayContractService
from app.services.openclaw.transport import GatewayTargetResolution


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


@dataclass
class RuntimeHarness:
    session: Session
    runtime_dir: Path
    service: GatewayContractService


def _build_gateway_contract_service(
    session: Session,
    runtime_dir: Path,
) -> GatewayContractService:
    return GatewayContractService(
        adapter=FakeAdapter(),
        intake_runtime_service=GatewayIntakeRuntimeService(
            IntakeRuntimeRepository(session, runtime_dir=runtime_dir)
        ),
    )


@contextmanager
def override_gateway_contract_service(service: object) -> Iterator[None]:
    app.dependency_overrides[get_gateway_contract_service] = lambda: service
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def runtime_harness(tmp_path: Path) -> Iterator[RuntimeHarness]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield RuntimeHarness(
            session=session,
            runtime_dir=tmp_path,
            service=_build_gateway_contract_service(session, tmp_path),
        )
    finally:
        session.close()


@pytest.fixture
def api_client(runtime_harness: RuntimeHarness) -> Iterator[TestClient]:
    with override_gateway_contract_service(runtime_harness.service):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture
def test_client() -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


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


def test_gateway_contract_endpoint_returns_metadata(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/gateway/contract")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.2.0"
    assert payload["runtime_mode"] == "multi-agent"
    assert payload["frontend_boundary"]["direct_browser_gateway_access"] is False
    assert payload["architecture_flow"] == "frontend -> Agentic-Workflow backend -> Gateway"
    assert [agent["agent_key"] for agent in payload["named_agents"]] == EXPECTED_ALL_AGENT_KEYS
    assert {
        agent["agent_key"]: agent["agent_role"] for agent in payload["named_agents"]
    } == EXPECTED_AGENT_ROLES
    assert any(item["name"] == "realtime-events" for item in payload["canonical_interfaces"])


def test_gateway_runtime_endpoint_returns_zero_bucket_intake_shape(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.2.0"
    assert payload["availability"] == "available"
    assert payload["runtime"]["runtime_mode"] == "multi-agent"
    assert payload["runtime"]["source_of_truth"] == "agentic-workflow+gateway"
    assert [
        agent["agent_key"] for agent in payload["runtime"]["agent_states"]
    ] == EXPECTED_ALL_AGENT_KEYS
    assert payload["runtime"]["agent_states"][0]["agent_role"] == "control-plane-coordinator"
    assert payload["runtime"]["agent_states"][0]["session_affinity"] == {
        "source_of_truth": "gateway",
        "session_id": "reserved-session-overlord",
        "route_key": "agent.overlord",
        "status": "reserved",
    }
    firehose = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "firehose"
    )
    assert firehose["queue"] == {
        "status": "live",
        "source_of_truth": "agentic-workflow",
        "pending_items": 0,
        "total_items": 0,
        "state_counts": {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
        },
        "checkpoint": {
            "kind": "firehose",
            "next_page": 1,
            "last_checkpointed_at": None,
            "mirror_snapshot_generated_at": None,
            "active_mode": None,
            "resume_required": None,
            "new_anchor_date": None,
            "trending_anchor_date": None,
            "run_started_at": None,
            "window_start_date": None,
            "created_before_boundary": None,
            "created_before_cursor": None,
            "exhausted": None,
        },
        "notes": [
            "Queue counts and checkpoint metadata come from Agentic-Workflow persistence.",
            "Gateway-owned routing and session fields remain backend-mediated on this surface.",
        ],
    }
    assert payload["runtime"]["agent_states"][-1]["session_affinity"] == {
        "source_of_truth": "gateway",
        "session_id": None,
        "route_key": None,
        "status": "reserved",
    }


def test_gateway_runtime_endpoint_returns_mixed_intake_status_from_backend_state(
    api_client: TestClient,
    runtime_harness: RuntimeHarness,
) -> None:
    _seed_runtime_state(runtime_harness.session)
    _write_runtime_snapshot(runtime_harness.runtime_dir, "firehose", "2026-03-07T10:16:00+00:00")
    _write_runtime_snapshot(runtime_harness.runtime_dir, "backfill", "2026-03-07T09:45:00+00:00")

    response = api_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    firehose = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "firehose"
    )
    backfill = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "backfill"
    )
    bouncer = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "bouncer"
    )

    assert firehose["queue"]["state_counts"] == {
        "pending": 1,
        "in_progress": 1,
        "completed": 0,
        "failed": 1,
    }
    assert firehose["queue"]["checkpoint"]["kind"] == "firehose"
    assert firehose["queue"]["checkpoint"]["active_mode"] == "trending"
    assert firehose["queue"]["checkpoint"]["next_page"] == 4
    assert firehose["queue"]["checkpoint"]["mirror_snapshot_generated_at"] == (
        "2026-03-07T10:16:00Z"
    )

    assert backfill["queue"]["state_counts"] == {
        "pending": 0,
        "in_progress": 1,
        "completed": 1,
        "failed": 0,
    }
    assert backfill["queue"]["checkpoint"]["kind"] == "backfill"
    assert backfill["queue"]["checkpoint"]["window_start_date"] == "2025-01-01"
    assert backfill["queue"]["checkpoint"]["created_before_boundary"] == "2025-01-31"
    assert backfill["queue"]["checkpoint"]["created_before_cursor"] == ("2025-01-15T12:00:00Z")

    assert bouncer["queue"]["status"] == "reserved"


def test_gateway_runtime_endpoint_handles_partial_firehose_progress_without_queue_rows(
    api_client: TestClient,
    runtime_harness: RuntimeHarness,
) -> None:
    runtime_harness.session.add(
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
    runtime_harness.session.commit()

    response = api_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    firehose = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "firehose"
    )
    assert firehose["queue"]["state_counts"] == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert firehose["queue"]["total_items"] == 0
    assert firehose["queue"]["checkpoint"]["kind"] == "firehose"
    assert firehose["queue"]["checkpoint"]["active_mode"] is None
    assert firehose["queue"]["checkpoint"]["next_page"] == 2
    assert firehose["queue"]["checkpoint"]["resume_required"] is False
    assert firehose["queue"]["checkpoint"]["run_started_at"] is None


def test_gateway_runtime_endpoint_handles_backfill_checkpoint_without_queue_rows(
    api_client: TestClient,
    runtime_harness: RuntimeHarness,
) -> None:
    runtime_harness.session.add(
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
    runtime_harness.session.commit()

    response = api_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    backfill = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "backfill"
    )
    assert backfill["queue"]["state_counts"] == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert backfill["queue"]["total_items"] == 0
    assert backfill["queue"]["checkpoint"]["kind"] == "backfill"
    assert backfill["queue"]["checkpoint"]["window_start_date"] == "2025-02-01"
    assert backfill["queue"]["checkpoint"]["created_before_boundary"] == "2025-02-28"
    assert backfill["queue"]["checkpoint"]["created_before_cursor"] is None
    assert backfill["queue"]["checkpoint"]["next_page"] == 4
    assert backfill["queue"]["checkpoint"]["exhausted"] is False


def test_gateway_runtime_endpoint_surfaces_snapshot_issue_notes(
    api_client: TestClient,
    runtime_harness: RuntimeHarness,
) -> None:
    firehose_dir = runtime_harness.runtime_dir / "firehose"
    firehose_dir.mkdir()
    (firehose_dir / "progress.json").write_text("{ invalid json", encoding="utf-8")

    response = api_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    firehose = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "firehose"
    )
    assert (
        "The runtime/firehose/progress.json mirror snapshot is currently invalid."
        in firehose["queue"]["notes"]
    )


def test_gateway_sessions_endpoint_returns_agent_mapped_placeholders(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/gateway/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.2.0"
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


def test_gateway_session_detail_endpoint_returns_agent_context_for_reserved_session(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/gateway/sessions/reserved-session-overlord")

    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "1.2.0",
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


def test_gateway_session_history_endpoint_returns_reserved_shape(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/gateway/sessions/demo-session/history")

    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "1.2.0",
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


def test_gateway_event_envelope_endpoint_returns_reserved_shape(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/gateway/events/envelope")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "1.2.0"
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


def test_gateway_contract_error_returns_structured_envelope(
    test_client: TestClient,
) -> None:
    class BrokenService:
        def get_contract_metadata(self) -> None:
            raise AppError(
                message="Gateway contract lookup failed.",
                code="gateway_contract_lookup_failed",
                status_code=503,
                details={"surface": "gateway-contract"},
            )

    with override_gateway_contract_service(BrokenService()):
        response = test_client.get("/api/v1/gateway/contract")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "gateway_contract_lookup_failed",
            "message": "Gateway contract lookup failed.",
            "details": {"surface": "gateway-contract"},
        }
    }


def test_gateway_contract_endpoint_returns_settings_validation_error_for_invalid_openclaw_config(
    test_client: TestClient,
    tmp_path: Path,
) -> None:
    from app.services.openclaw.transport import resolve_gateway_target

    config_path = tmp_path / "openclaw.json"
    config_path.write_text("{ invalid json", encoding="utf-8")

    class SettingsBackedAdapter:
        def resolve_transport_target(self):
            return resolve_gateway_target(
                Settings(
                    OPENCLAW_CONFIG_PATH=config_path,
                )
            )

    with override_gateway_contract_service(GatewayContractService(adapter=SettingsBackedAdapter())):
        response = test_client.get("/api/v1/gateway/contract")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "settings_validation_failed"
    assert payload["error"]["details"]["validation"]["issues"][0]["field"] == "OPENCLAW_CONFIG_PATH"


def test_gateway_runtime_endpoint_returns_intake_surface_for_invalid_gateway_url(
    test_client: TestClient,
    runtime_harness: RuntimeHarness,
    tmp_path: Path,
) -> None:
    from app.services.openclaw.transport import resolve_gateway_target

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
                "agents": {"defaults": {"model": {"primary": "test-model"}}},
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

    service = GatewayContractService(
        adapter=SettingsBackedAdapter(),
        intake_runtime_service=GatewayIntakeRuntimeService(
            IntakeRuntimeRepository(
                runtime_harness.session,
                runtime_dir=runtime_harness.runtime_dir,
            )
        ),
    )

    with override_gateway_contract_service(service):
        response = test_client.get("/api/v1/gateway/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["availability"] == "available"
    assert payload["runtime"]["gateway_url"] is None
    firehose = next(
        agent for agent in payload["runtime"]["agent_states"] if agent["agent_key"] == "firehose"
    )
    assert firehose["queue"]["status"] == "live"


def test_gateway_sessions_error_returns_structured_envelope(
    test_client: TestClient,
) -> None:
    class BrokenService:
        def get_session_surface(self) -> None:
            raise AppError(
                message="Gateway sessions surface failed.",
                code="gateway_sessions_surface_failed",
                status_code=503,
                details={"surface": "gateway-sessions"},
            )

    with override_gateway_contract_service(BrokenService()):
        response = test_client.get("/api/v1/gateway/sessions")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "gateway_sessions_surface_failed",
            "message": "Gateway sessions surface failed.",
            "details": {"surface": "gateway-sessions"},
        }
    }


def _write_runtime_snapshot(runtime_dir: Path, intake_key: str, generated_at: str) -> None:
    intake_dir = runtime_dir / intake_key
    intake_dir.mkdir()
    (intake_dir / "progress.json").write_text(
        json.dumps({"generated_at": generated_at}),
        encoding="utf-8",
    )


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
