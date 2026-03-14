import pytest
from collections.abc import Iterator
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app
from app.api.deps import get_memory_service, get_session
from app.models.repository import ObsessionContext, IdeaFamily
from app.repositories.memory_repository import MemoryRepository
from app.repositories.obsession_repository import ObsessionRepository
from app.services.memory_service import MemoryService


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import event
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

    def get_test_memory_service():
        return MemoryService(
            MemoryRepository(db_session),
            ObsessionRepository(db_session),
        )

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_memory_service] = get_test_memory_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def obsession_context(db_session: Session) -> ObsessionContext:
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.commit()
    db_session.refresh(family)

    context = ObsessionContext(title="Test Context", idea_family_id=family.id)
    db_session.add(context)
    db_session.commit()
    db_session.refresh(context)
    return context

def test_write_memory_segment(client: TestClient, obsession_context: ObsessionContext):
    response = client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={
            "segment_key": "insights",
            "content": "Test insights",
            "content_type": "markdown",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["segment_key"] == "insights"
    assert data["content"] == "Test insights"
    assert data["content_type"] == "markdown"


def test_write_memory_segment_context_not_found(client: TestClient):
    response = client.post(
        "/api/v1/obsession/contexts/99999/memory",
        json={
            "segment_key": "test",
            "content": "content",
            "content_type": "markdown",
        },
    )

    assert response.status_code == 404


def test_list_memory_segments(client: TestClient, obsession_context: ObsessionContext):
    client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={"segment_key": "insights", "content": "Content 1", "content_type": "markdown"},
    )
    client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={"segment_key": "patterns", "content": "Content 2", "content_type": "json"},
    )

    response = client.get(f"/api/v1/obsession/contexts/{obsession_context.id}/memory")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {seg["segment_key"] for seg in data} == {"insights", "patterns"}


def test_read_memory_segment(client: TestClient, obsession_context: ObsessionContext):
    client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={"segment_key": "next_steps", "content": "Step 1", "content_type": "markdown"},
    )

    response = client.get(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory/next_steps"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["segment_key"] == "next_steps"
    assert data["content"] == "Step 1"


def test_read_memory_segment_not_found(client: TestClient, obsession_context: ObsessionContext):
    response = client.get(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory/nonexistent"
    )

    assert response.status_code == 404


def test_delete_memory_segment(client: TestClient, obsession_context: ObsessionContext):
    client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={"segment_key": "temp", "content": "Temporary", "content_type": "markdown"},
    )

    response = client.delete(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory/temp"
    )

    assert response.status_code == 204

    get_response = client.get(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory/temp"
    )
    assert get_response.status_code == 404


def test_memory_isolation_between_contexts(client: TestClient, db_session: Session):
    family = IdeaFamily(title="Test Family")
    db_session.add(family)
    db_session.commit()
    db_session.refresh(family)

    context1 = ObsessionContext(title="Context 1", idea_family_id=family.id)
    context2 = ObsessionContext(title="Context 2", idea_family_id=family.id)
    db_session.add_all([context1, context2])
    db_session.commit()
    db_session.refresh(context1)
    db_session.refresh(context2)

    client.post(
        f"/api/v1/obsession/contexts/{context1.id}/memory",
        json={"segment_key": "shared", "content": "Context 1 content", "content_type": "markdown"},
    )
    client.post(
        f"/api/v1/obsession/contexts/{context2.id}/memory",
        json={"segment_key": "shared", "content": "Context 2 content", "content_type": "markdown"},
    )

    response1 = client.get(f"/api/v1/obsession/contexts/{context1.id}/memory/shared")
    response2 = client.get(f"/api/v1/obsession/contexts/{context2.id}/memory/shared")

    assert response1.json()["content"] == "Context 1 content"
    assert response2.json()["content"] == "Context 2 content"


def test_write_memory_segment_exceeds_size_limit(client: TestClient, obsession_context: ObsessionContext):
    large_content = "x" * 51201  # 50KB + 1 byte
    response = client.post(
        f"/api/v1/obsession/contexts/{obsession_context.id}/memory",
        json={
            "segment_key": "large",
            "content": large_content,
            "content_type": "markdown",
        },
    )

    assert response.status_code == 422
    response_data = response.json()
    assert "50KB limit" in str(response_data)
