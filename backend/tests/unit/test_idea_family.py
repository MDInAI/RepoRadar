import pytest
from datetime import datetime, timezone

from sqlalchemy import select
from app.core.errors import AppError
from app.models.repository import IdeaFamily, IdeaFamilyMembership, RepositoryIntake
from app.repositories.idea_family_repository import IdeaFamilyRepository


def test_create_family(session):
    repo = IdeaFamilyRepository(session)
    record = repo.create_family("AI Tools", "Collection of AI-powered tools")

    assert record.id is not None
    assert record.title == "AI Tools"
    assert record.description == "Collection of AI-powered tools"
    assert record.created_at is not None
    assert record.updated_at is not None


def test_get_family(session):
    repo = IdeaFamilyRepository(session)
    created = repo.create_family("Test Family", None)

    fetched = repo.get_family(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "Test Family"


def test_get_family_not_found(session):
    repo = IdeaFamilyRepository(session)
    result = repo.get_family(99999)
    assert result is None


def test_list_families(session):
    repo = IdeaFamilyRepository(session)
    repo.create_family("Family 1", None)
    repo.create_family("Family 2", "Description")

    families = repo.list_families()
    assert len(families) >= 2
    assert any(f.title == "Family 1" for f in families)
    assert any(f.title == "Family 2" for f in families)


def test_update_family(session):
    repo = IdeaFamilyRepository(session)
    created = repo.create_family("Original", "Original desc")

    updated = repo.update_family(created.id, "Updated", "Updated desc")
    assert updated.title == "Updated"
    assert updated.description == "Updated desc"
    assert updated.updated_at > created.updated_at


def test_update_family_not_found(session):
    repo = IdeaFamilyRepository(session)
    with pytest.raises(AppError) as exc:
        repo.update_family(99999, "Title", None)
    assert exc.value.status_code == 404


def test_delete_family(session):
    repo = IdeaFamilyRepository(session)
    created = repo.create_family("To Delete", None)

    repo.delete_family(created.id)
    assert repo.get_family(created.id) is None


def test_delete_family_cascades_memberships(session):
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
    session.flush()

    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test Family", None)
    repo.add_repository(family.id, 12345)

    # Verify membership exists
    stmt = select(IdeaFamilyMembership).where(IdeaFamilyMembership.idea_family_id == family.id)
    memberships_before = session.exec(stmt).all()
    assert len(memberships_before) == 1

    # Delete family
    repo.delete_family(family.id)

    # Verify memberships are cascade-deleted
    stmt = select(IdeaFamilyMembership).where(IdeaFamilyMembership.idea_family_id == family.id)
    memberships_after = session.exec(stmt).all()
    assert len(memberships_after) == 0


def test_delete_family_not_found(session):
    repo = IdeaFamilyRepository(session)
    with pytest.raises(AppError) as exc:
        repo.delete_family(99999)
    assert exc.value.status_code == 404


def test_add_repository(session):
    # Create test repository
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
    session.flush()

    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test Family", None)

    membership = repo.add_repository(family.id, 12345)
    assert membership.idea_family_id == family.id
    assert membership.github_repository_id == 12345


def test_add_repository_family_not_found(session):
    repo = IdeaFamilyRepository(session)
    with pytest.raises(AppError) as exc:
        repo.add_repository(99999, 12345)
    assert exc.value.status_code == 404


def test_add_repository_repo_not_found(session):
    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test", None)

    with pytest.raises(AppError) as exc:
        repo.add_repository(family.id, 99999)
    assert exc.value.status_code == 404


def test_add_repository_duplicate(session):
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
    session.flush()

    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test", None)
    repo.add_repository(family.id, 12345)

    with pytest.raises(AppError) as exc:
        repo.add_repository(family.id, 12345)
    assert exc.value.status_code == 409


def test_remove_repository(session):
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
    session.flush()

    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test", None)
    repo.add_repository(family.id, 12345)

    repo.remove_repository(family.id, 12345)
    repos = repo.list_family_repositories(family.id)
    assert 12345 not in repos


def test_remove_repository_not_found(session):
    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test", None)

    with pytest.raises(AppError) as exc:
        repo.remove_repository(family.id, 99999)
    assert exc.value.status_code == 404


def test_list_family_repositories(session):
    intake1 = RepositoryIntake(
        github_repository_id=12345,
        source_provider="github",
        owner_login="test",
        repository_name="repo1",
        full_name="test/repo1",
        stargazers_count=100,
        forks_count=10,
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
        discovered_at=datetime.now(timezone.utc),
        status_updated_at=datetime.now(timezone.utc),
    )
    session.add(intake1)
    session.add(intake2)
    session.flush()

    repo = IdeaFamilyRepository(session)
    family = repo.create_family("Test", None)
    repo.add_repository(family.id, 12345)
    repo.add_repository(family.id, 67890)

    repos = repo.list_family_repositories(family.id)
    assert 12345 in repos
    assert 67890 in repos


def test_list_repository_families(session):
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
    session.flush()

    repo = IdeaFamilyRepository(session)
    family1 = repo.create_family("Family 1", None)
    family2 = repo.create_family("Family 2", None)
    repo.add_repository(family1.id, 12345)
    repo.add_repository(family2.id, 12345)

    families = repo.list_repository_families(12345)
    assert family1.id in families
    assert family2.id in families
