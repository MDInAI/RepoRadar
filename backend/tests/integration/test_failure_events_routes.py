from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.api.deps import get_agent_event_service
from app.main import app
from app.models import EventSeverity
from app.models.agent_event import FailureClassification, FailureSeverity
from app.models.agent_event import SystemEvent
from app.repositories.agent_event_repository import AgentEventRepository
from app.services.agent_event_service import AgentEventService


def _build_service(session: Session) -> AgentEventService:
    return AgentEventService(AgentEventRepository(session), broadcaster=None)


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_agent_event_service] = lambda: _build_service(db_session)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _seed_failure_events(session: Session) -> None:
    session.add_all(
        [
            SystemEvent(
                id=1,
                event_type="rate_limit_hit",
                agent_name="firehose",
                severity=EventSeverity.ERROR,
                message="firehose hit the GitHub rate limit and backed off.",
                context_json='{"page": 3, "retry_after_seconds": 60}',
                failure_classification=FailureClassification.RATE_LIMITED,
                failure_severity=FailureSeverity.ERROR,
                http_status_code=429,
                retry_after_seconds=60,
                upstream_provider="github",
                created_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
            ),
            SystemEvent(
                id=2,
                event_type="rate_limit_hit",
                agent_name="backfill",
                severity=EventSeverity.ERROR,
                message="backfill hit the GitHub rate limit and backed off.",
                context_json='{"page": 1, "retry_after_seconds": 30}',
                failure_classification=FailureClassification.RATE_LIMITED,
                failure_severity=FailureSeverity.ERROR,
                http_status_code=403,
                retry_after_seconds=30,
                upstream_provider="github",
                created_at=datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
            ),
            SystemEvent(
                id=3,
                event_type="analysis_failed",
                agent_name="analyst",
                severity=EventSeverity.WARNING,
                message="LLM call timed out for repository 42.",
                failure_classification=FailureClassification.RETRYABLE,
                failure_severity=FailureSeverity.WARNING,
                affected_repository_id=42,
                upstream_provider="llm",
                created_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            ),
            SystemEvent(
                id=4,
                event_type="agent_started",
                agent_name="firehose",
                severity=EventSeverity.INFO,
                message="firehose run started.",
                # No failure fields — a normal lifecycle event
                created_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()


def test_failure_events_endpoint_returns_only_classified_events(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get("/api/v1/events/failures")

    assert response.status_code == 200
    events = response.json()
    # Only the 3 events with failure_classification set are returned (not event id=4)
    assert len(events) == 3
    assert {e["id"] for e in events} == {1, 2, 3}


def test_failure_events_include_all_context_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get("/api/v1/events/failures", params={"agent_name": "firehose"})

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    event = events[0]
    assert event["id"] == 1
    assert event["event_type"] == "rate_limit_hit"
    assert event["failure_classification"] == "rate_limited"
    assert event["failure_severity"] == "error"
    assert event["http_status_code"] == 429
    assert event["retry_after_seconds"] == 60
    assert event["upstream_provider"] == "github"
    assert event["affected_repository_id"] is None


def test_failure_events_filter_by_classification(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get("/api/v1/events/failures", params={"classification": "retryable"})

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["id"] == 3
    assert events[0]["failure_classification"] == "retryable"
    assert events[0]["affected_repository_id"] == 42
    assert events[0]["upstream_provider"] == "llm"


def test_failure_events_filter_by_severity(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get("/api/v1/events/failures", params={"severity": "error"})

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
    assert {e["id"] for e in events} == {1, 2}
    assert all(e["failure_severity"] == "error" for e in events)


def test_failure_events_filter_by_since(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get(
        "/api/v1/events/failures",
        params={"since": "2026-03-10T11:30:00Z"},
    )

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["id"] == 3


def test_failure_events_returns_empty_list_when_no_classified_events(
    client: TestClient,
    db_session: Session,
) -> None:
    # Only the lifecycle event (no failure_classification)
    db_session.add(
        SystemEvent(
            id=1,
            event_type="agent_started",
            agent_name="firehose",
            severity=EventSeverity.INFO,
            message="firehose run started.",
            created_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/api/v1/events/failures")

    assert response.status_code == 200
    assert response.json() == []


def test_failure_events_limit_param_is_respected(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_failure_events(db_session)

    response = client.get("/api/v1/events/failures", params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_failure_events_rejects_limit_above_maximum(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/events/failures", params={"limit": 201})
    assert response.status_code == 422
