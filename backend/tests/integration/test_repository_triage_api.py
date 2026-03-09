from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.api.routes.repositories import get_repository_triage_service
from app.main import app
from app.models import (
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)
from app.repositories.repository_triage_repository import RepositoryTriageRepository
from app.services.repository_triage_service import RepositoryTriageService


@dataclass
class TriageApiHarness:
    session: Session


def _build_repository_triage_service(session: Session) -> RepositoryTriageService:
    return RepositoryTriageService(RepositoryTriageRepository(session))


@contextmanager
def override_repository_triage_service(service: object) -> Iterator[None]:
    app.dependency_overrides[get_repository_triage_service] = lambda: service
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def triage_harness() -> Iterator[TriageApiHarness]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield TriageApiHarness(session=session)
    finally:
        session.close()


@pytest.fixture
def api_client(triage_harness: TriageApiHarness) -> Iterator[TestClient]:
    service = _build_repository_triage_service(triage_harness.session)
    with override_repository_triage_service(service):
        with TestClient(app) as test_client:
            yield test_client


def test_repository_triage_endpoint_returns_accepted_snapshot(
    api_client: TestClient,
    triage_harness: TriageApiHarness,
) -> None:
    _seed_repository(
        triage_harness.session,
        repository_id=101,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        triaged_at=datetime(2026, 3, 8, 12, 30, tzinfo=timezone.utc),
        explanation=RepositoryTriageExplanation(
            github_repository_id=101,
            explanation_kind=RepositoryTriageExplanationKind.INCLUDE_RULE,
            explanation_summary="Accepted because include rules matched: saas.",
            matched_include_rules=["saas"],
            matched_exclude_rules=[],
            explained_at=datetime(2026, 3, 8, 12, 30, tzinfo=timezone.utc),
        ),
    )

    response = api_client.get("/api/v1/repositories/101/triage")

    assert response.status_code == 200
    assert response.json() == {
        "triage_status": "accepted",
        "triaged_at": "2026-03-08T12:30:00Z",
        "explanation": {
            "kind": "include_rule",
            "summary": "Accepted because include rules matched: saas.",
            "matched_include_rules": ["saas"],
            "matched_exclude_rules": [],
            "explained_at": "2026-03-08T12:30:00Z",
        },
    }


def test_repository_triage_endpoint_returns_rejected_snapshot(
    api_client: TestClient,
    triage_harness: TriageApiHarness,
) -> None:
    _seed_repository(
        triage_harness.session,
        repository_id=202,
        triage_status=RepositoryTriageStatus.REJECTED,
        triaged_at=datetime(2026, 3, 8, 12, 45, tzinfo=timezone.utc),
        explanation=RepositoryTriageExplanation(
            github_repository_id=202,
            explanation_kind=RepositoryTriageExplanationKind.EXCLUDE_RULE,
            explanation_summary="Rejected because exclude rules matched: tutorial.",
            matched_include_rules=[],
            matched_exclude_rules=["tutorial"],
            explained_at=datetime(2026, 3, 8, 12, 45, tzinfo=timezone.utc),
        ),
    )

    response = api_client.get("/api/v1/repositories/202/triage")

    assert response.status_code == 200
    assert response.json() == {
        "triage_status": "rejected",
        "triaged_at": "2026-03-08T12:45:00Z",
        "explanation": {
            "kind": "exclude_rule",
            "summary": "Rejected because exclude rules matched: tutorial.",
            "matched_include_rules": [],
            "matched_exclude_rules": ["tutorial"],
            "explained_at": "2026-03-08T12:45:00Z",
        },
    }


def test_repository_triage_endpoint_returns_pending_without_fake_explanation(
    api_client: TestClient,
    triage_harness: TriageApiHarness,
) -> None:
    _seed_repository(
        triage_harness.session,
        repository_id=303,
        triage_status=RepositoryTriageStatus.PENDING,
        triaged_at=None,
        explanation=None,
    )

    response = api_client.get("/api/v1/repositories/303/triage")

    assert response.status_code == 200
    assert response.json() == {
        "triage_status": "pending",
        "triaged_at": None,
        "explanation": None,
    }


def test_repository_triage_endpoint_returns_structured_not_found_error(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/repositories/404/triage")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "repository_not_found",
            "message": "Repository 404 was not found.",
            "details": {"github_repository_id": 404},
        }
    }


def _seed_repository(
    session: Session,
    *,
    repository_id: int,
    triage_status: RepositoryTriageStatus,
    triaged_at: datetime | None,
    explanation: RepositoryTriageExplanation | None,
) -> None:
    owner_login = f"owner-{repository_id}"
    repository_name = f"repo-{repository_id}"
    session.add(
        RepositoryIntake(
            github_repository_id=repository_id,
            owner_login=owner_login,
            repository_name=repository_name,
            full_name=f"{owner_login}/{repository_name}",
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=triage_status,
            discovered_at=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
            queue_created_at=datetime(2026, 3, 8, 11, 0, tzinfo=timezone.utc),
            status_updated_at=datetime(2026, 3, 8, 11, 30, tzinfo=timezone.utc),
            triaged_at=triaged_at,
        )
    )
    if explanation is not None:
        session.add(explanation)
    session.commit()
