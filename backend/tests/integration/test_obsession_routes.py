import pytest
from collections.abc import Iterator
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app
from app.api.deps import get_session, get_obsession_service
from app.models.repository import IdeaFamily, ObsessionContext
from app.repositories.obsession_repository import ObsessionRepository
from app.repositories.idea_family_repository import IdeaFamilyRepository
from app.repositories.synthesis_repository import SynthesisRepository
from app.services.obsession_service import ObsessionService


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

    def get_test_obsession_service():
        return ObsessionService(
            ObsessionRepository(db_session),
            IdeaFamilyRepository(db_session),
            SynthesisRepository(db_session)
        )

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_obsession_service] = get_test_obsession_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_create_obsession_context(client: TestClient, db_session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.commit()

    response = client.post(
        "/api/v1/obsession/contexts",
        json={
            "idea_family_id": family.id,
            "title": "Test Context",
            "description": "Test description",
            "refresh_policy": "manual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Context"
    assert data["description"] == "Test description"
    assert data["status"] == "active"
    assert data["refresh_policy"] == "manual"
    assert data["synthesis_run_count"] == 0


def test_create_obsession_context_family_not_found(client: TestClient):
    response = client.post(
        "/api/v1/obsession/contexts",
        json={
            "idea_family_id": 99999,
            "title": "Test",
            "refresh_policy": "manual",
        },
    )

    assert response.status_code == 404


def test_create_obsession_context_invalid_refresh_policy(client: TestClient, db_session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.commit()

    response = client.post(
        "/api/v1/obsession/contexts",
        json={
            "idea_family_id": family.id,
            "title": "Test",
            "refresh_policy": "invalid",
        },
    )

    assert response.status_code == 422


def test_list_obsession_contexts(client: TestClient, db_session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.flush()

    ctx1 = ObsessionContext(idea_family_id=family.id, title="Context 1", refresh_policy="manual")
    ctx2 = ObsessionContext(idea_family_id=family.id, title="Context 2", refresh_policy="daily")
    db_session.add_all([ctx1, ctx2])
    db_session.commit()

    response = client.get("/api/v1/obsession/contexts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_obsession_contexts_filtered(client: TestClient, db_session):
    family1 = IdeaFamily(title="Family 1")
    family2 = IdeaFamily(title="Family 2")
    db_session.add_all([family1, family2])
    db_session.flush()

    ctx1 = ObsessionContext(idea_family_id=family1.id, title="Context 1", refresh_policy="manual")
    ctx2 = ObsessionContext(idea_family_id=family2.id, title="Context 2", refresh_policy="manual")
    db_session.add_all([ctx1, ctx2])
    db_session.commit()

    response = client.get(f"/api/v1/obsession/contexts?idea_family_id={family1.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["idea_family_id"] == family1.id


def test_get_obsession_context(client: TestClient, db_session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.flush()

    context = ObsessionContext(idea_family_id=family.id, title="Test", refresh_policy="manual")
    db_session.add(context)
    db_session.commit()

    response = client.get(f"/api/v1/obsession/contexts/{context.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == context.id
    assert data["title"] == "Test"
    assert data["memory_segment_count"] == 0
    assert "synthesis_runs" in data
    assert "family_title" in data
    assert "repository_count" in data
    assert "repositories" in data
    assert "scope_updated_at" in data
    assert isinstance(data["repositories"], list)


def test_get_obsession_context_not_found(client: TestClient):
    response = client.get("/api/v1/obsession/contexts/99999")
    assert response.status_code == 404


def test_update_obsession_context(client: TestClient, db_session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.flush()

    context = ObsessionContext(idea_family_id=family.id, title="Original", refresh_policy="manual")
    db_session.add(context)
    db_session.commit()

    response = client.put(
        f"/api/v1/obsession/contexts/{context.id}",
        json={"title": "Updated", "status": "paused"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["status"] == "paused"


def test_trigger_refresh(client: TestClient, db_session):
    from app.models.repository import RepositoryIntake, IdeaFamilyMembership

    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.flush()

    repo = RepositoryIntake(
        github_repository_id=123,
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
    )
    db_session.add(repo)
    db_session.flush()

    membership = IdeaFamilyMembership(idea_family_id=family.id, github_repository_id=123)
    db_session.add(membership)
    db_session.flush()

    context = ObsessionContext(idea_family_id=family.id, title="Test", refresh_policy="manual")
    db_session.add(context)
    db_session.commit()

    response = client.post(f"/api/v1/obsession/contexts/{context.id}/refresh")
    assert response.status_code == 201
    data = response.json()
    assert "synthesis_run_id" in data
    assert isinstance(data["synthesis_run_id"], int)
