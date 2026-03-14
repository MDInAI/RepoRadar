from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db_session
from app.main import app
from app.models.repository import IdeaFamily, SynthesisRun


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def get_test_session():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = get_test_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def sample_family(db_session: Session) -> IdeaFamily:
    family = IdeaFamily(title="Test Family", description="Test description")
    db_session.add(family)
    db_session.commit()
    db_session.refresh(family)
    return family


@pytest.fixture
def sample_runs(db_session: Session, sample_family: IdeaFamily) -> list[SynthesisRun]:
    runs = [
        SynthesisRun(
            idea_family_id=sample_family.id,
            run_type="combiner",
            status="completed",
            input_repository_ids=[10, 20],
            output_text="Output 1",
            title="Run 1",
            summary="Summary about AI",
            key_insights=["Insight A"],
            started_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 10, 10, 5, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
        ),
        SynthesisRun(
            idea_family_id=sample_family.id,
            run_type="obsession",
            status="failed",
            input_repository_ids=[30],
            output_text=None,
            title="Run 2",
            summary=None,
            key_insights=None,
            error_message="Error",
            started_at=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=None,
            created_at=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    for run in runs:
        db_session.add(run)
    db_session.commit()
    for run in runs:
        db_session.refresh(run)
    return runs


def test_list_runs_rejects_invalid_status(client: TestClient):
    response = client.get("/api/v1/synthesis/runs", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_list_runs_rejects_invalid_date(client: TestClient):
    response = client.get("/api/v1/synthesis/runs", params={"date_from": "not-a-date"})

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_FILTER_PARAMETERS"
    assert "Invalid date_from format" in data["error"]["message"]


def test_list_runs_filters_by_status(client: TestClient, sample_runs: list[SynthesisRun]):
    response = client.get("/api/v1/synthesis/runs", params={"status": "completed", "idea_family_id": sample_runs[0].idea_family_id})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "completed"


def test_list_runs_filters_by_search(client: TestClient, sample_runs: list[SynthesisRun]):
    response = client.get("/api/v1/synthesis/runs", params={"search": "AI", "idea_family_id": sample_runs[0].idea_family_id})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "AI" in data[0]["summary"]


def test_list_runs_filters_by_date_range(client: TestClient, sample_runs: list[SynthesisRun]):
    response = client.get("/api/v1/synthesis/runs", params={"date_from": "2026-03-11", "idea_family_id": sample_runs[0].idea_family_id})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Run 2"


def test_list_runs_filters_by_repository(client: TestClient, sample_runs: list[SynthesisRun]):
    response = client.get("/api/v1/synthesis/runs", params={"repository_id": 30, "idea_family_id": sample_runs[0].idea_family_id})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert 30 in data[0]["input_repository_ids"]


def test_trigger_combiner_rejects_duplicate_repositories(client: TestClient, sample_family: IdeaFamily):
    response = client.post(
        "/api/v1/synthesis/combiner",
        json={"repository_ids": [10, 20, 10]}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "DUPLICATE_REPOSITORIES"
    assert "Duplicate repository IDs" in data["error"]["message"]

