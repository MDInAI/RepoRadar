import pytest
from collections.abc import Iterator
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.main import app
from app.api.deps import get_idea_family_service, get_session
from app.models.repository import RepositoryIntake
from app.repositories.idea_family_repository import IdeaFamilyRepository
from app.services.idea_family_service import IdeaFamilyService


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable foreign keys for SQLite
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

    def get_test_idea_family_service():
        return IdeaFamilyService(IdeaFamilyRepository(db_session))

    from app.api.deps import get_repository_exploration_service
    from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
    from app.services.repository_exploration_service import RepositoryExplorationService

    def get_test_repository_exploration_service():
        return RepositoryExplorationService(RepositoryExplorationRepository(db_session))

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_idea_family_service] = get_test_idea_family_service
    app.dependency_overrides[get_repository_exploration_service] = get_test_repository_exploration_service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def session(db_session: Session) -> Session:
    return db_session


def test_create_family(client: TestClient):
    response = client.post(
        "/api/v1/idea-families/",
        json={"title": "AI Tools", "description": "Collection of AI tools"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "AI Tools"
    assert data["description"] == "Collection of AI tools"
    assert data["member_count"] == 0
    assert "id" in data


def test_create_family_empty_title(client: TestClient):
    response = client.post(
        "/api/v1/idea-families/",
        json={"title": "   ", "description": "Test"},
    )
    assert response.status_code == 422


def test_list_families(client: TestClient, session):
    client.post("/api/v1/idea-families/", json={"title": "Family 1"})
    client.post("/api/v1/idea-families/", json={"title": "Family 2"})

    response = client.get("/api/v1/idea-families/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_get_family(client: TestClient):
    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test Family"},
    )
    family_id = create_response.json()["id"]

    response = client.get(f"/api/v1/idea-families/{family_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == family_id
    assert data["title"] == "Test Family"


def test_get_family_not_found(client: TestClient):
    response = client.get("/api/v1/idea-families/99999")
    assert response.status_code == 404


def test_update_family(client: TestClient):
    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Original"},
    )
    family_id = create_response.json()["id"]

    response = client.put(
        f"/api/v1/idea-families/{family_id}",
        json={"title": "Updated", "description": "New desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated"
    assert data["description"] == "New desc"


def test_delete_family(client: TestClient):
    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "To Delete"},
    )
    family_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/idea-families/{family_id}")
    assert response.status_code == 204

    get_response = client.get(f"/api/v1/idea-families/{family_id}")
    assert get_response.status_code == 404


def test_add_repository_to_family(client: TestClient, session):
    intake = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
        stargazers_count=100,
        forks_count=10,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake)
    session.commit()

    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test Family"},
    )
    family_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )
    assert response.status_code == 201

    get_response = client.get(f"/api/v1/idea-families/{family_id}")
    assert get_response.json()["member_count"] == 1


def test_add_repository_duplicate(client: TestClient, session):
    intake = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
        stargazers_count=100,
        forks_count=10,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake)
    session.commit()

    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test"},
    )
    family_id = create_response.json()["id"]

    client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )

    response = client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )
    assert response.status_code == 409


def test_remove_repository_from_family(client: TestClient, session):
    intake = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
        stargazers_count=100,
        forks_count=10,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake)
    session.commit()

    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test"},
    )
    family_id = create_response.json()["id"]

    client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )

    response = client.delete(f"/api/v1/idea-families/{family_id}/members/12345")
    assert response.status_code == 204

    get_response = client.get(f"/api/v1/idea-families/{family_id}")
    assert get_response.json()["member_count"] == 0


def test_catalog_filter_by_family(client: TestClient, session):
    from app.models.repository import RepositoryTriageStatus, RepositoryAnalysisStatus

    intake1 = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo1",
        full_name="test/repo1",
        stargazers_count=100,
        forks_count=10,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        analysis_status=RepositoryAnalysisStatus.COMPLETED,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    intake2 = RepositoryIntake(
        github_repository_id=67890,
        source_provider="github",
        owner_login="test",
        repository_name="repo2",
        full_name="test/repo2",
        stargazers_count=200,
        forks_count=20,
        triage_status=RepositoryTriageStatus.ACCEPTED,
        analysis_status=RepositoryAnalysisStatus.COMPLETED,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake1)
    session.add(intake2)
    session.commit()

    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test Family"},
    )
    family_id = create_response.json()["id"]

    client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )

    response = client.get(f"/api/v1/repositories?idea_family_id={family_id}")
    if response.status_code != 200:
        print(f"Error response: {response.json()}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
    assert any(item["github_repository_id"] == 12345 for item in data["items"])


def test_repository_detail_includes_families(client: TestClient, session):
    intake = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo",
        full_name="test/repo",
        stargazers_count=100,
        forks_count=10,
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake)
    session.commit()

    create_response = client.post(
        "/api/v1/idea-families/",
        json={"title": "Test Family"},
    )
    family_id = create_response.json()["id"]

    client.post(
        f"/api/v1/idea-families/{family_id}/members",
        json={"github_repository_id": 12345},
    )

    response = client.get("/api/v1/repositories/12345")
    assert response.status_code == 200
    data = response.json()
    assert family_id in data["idea_family_ids"]
