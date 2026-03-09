from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from app.core.errors import AppError
from app.models import RepositoryIntake, SQLModel
from app.repositories.repository_curation_repository import RepositoryCurationRepository
from app.services.repository_curation_service import RepositoryCurationService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'repository-curation.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_repository(session: Session, github_repository_id: int = 701) -> None:
    session.add(
        RepositoryIntake(
            github_repository_id=github_repository_id,
            owner_login="alpha",
            repository_name="growth-engine",
            full_name="alpha/growth-engine",
        )
    )
    session.commit()


def test_star_toggle_supports_initial_star_unstar_and_idempotent_restar(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_repository(session)
        service = RepositoryCurationService(RepositoryCurationRepository(session))

        first_star = service.set_repository_starred(701, True)
        second_star = service.set_repository_starred(701, True)
        unstarred = service.set_repository_starred(701, False)

    assert first_star.is_starred is True
    assert first_star.starred_at is not None
    assert second_star.is_starred is True
    assert second_star.starred_at is not None
    assert unstarred.is_starred is False
    assert unstarred.starred_at is None


def test_user_tag_lifecycle_rejects_duplicates_and_supports_removal(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_repository(session)
        service = RepositoryCurationService(RepositoryCurationRepository(session))

        created = service.add_repository_user_tag(701, "workflow")
        snapshot = service.get_repository_curation(701)

        with pytest.raises(AppError, match="already exists"):
            service.add_repository_user_tag(701, "workflow")

        service.remove_repository_user_tag(701, "workflow")
        cleared = service.get_repository_curation(701)

    assert created.tag_label == "workflow"
    assert snapshot.user_tags == ["workflow"]
    assert cleared.user_tags == []


def test_missing_repository_operations_raise_not_found(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        service = RepositoryCurationService(RepositoryCurationRepository(session))

        with pytest.raises(AppError, match="was not found"):
            service.get_repository_curation(999)

        with pytest.raises(AppError, match="was not found"):
            service.set_repository_starred(999, True)

        with pytest.raises(AppError, match="was not found"):
            service.add_repository_user_tag(999, "workflow")
