from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.providers.github_provider import DiscoveredRepository, FirehoseMode
from agentic_workers.storage.backend_models import (
    IdeaSearch,
    IdeaSearchDirection,
    IdeaSearchDiscovery,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    SQLModel,
)
from agentic_workers.storage.idea_search_intake import persist_idea_scout_batch
from agentic_workers.storage.repository_intake import (
    IntakePersistenceError,
    persist_backfill_batch,
    persist_firehose_batch,
)


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'repository-intake.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_persist_duplicate_repository_refreshes_metadata_without_resetting_state(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        persist_firehose_batch(
            session,
            [
                DiscoveredRepository(
                    github_repository_id=101,
                    owner_login="octocat",
                    repository_name="repo-101",
                    full_name="octocat/repo-101",
                    created_at=datetime(2026, 3, 7, 10, 0, tzinfo=timezone.utc),
                    description="Original description",
                    stargazers_count=10,
                    forks_count=2,
                    pushed_at=datetime(2026, 3, 7, 11, 0, tzinfo=timezone.utc),
                    firehose_discovery_mode=FirehoseMode.NEW,
                )
            ],
            mode=FirehoseMode.NEW,
        )
        existing = session.get(RepositoryIntake, 101)
        assert existing is not None
        existing.queue_status = RepositoryQueueStatus.COMPLETED
        existing.processing_started_at = datetime(2026, 3, 7, 10, 5, tzinfo=timezone.utc)
        existing.processing_completed_at = datetime(2026, 3, 7, 10, 15, tzinfo=timezone.utc)
        existing.status_updated_at = datetime(2026, 3, 7, 10, 15, tzinfo=timezone.utc)
        original_queue_created_at = existing.queue_created_at
        original_completed_at = existing.processing_completed_at
        original_status_updated_at = existing.status_updated_at
        session.add(existing)
        session.commit()

        result = persist_backfill_batch(
            session,
            [
                DiscoveredRepository(
                    github_repository_id=101,
                    owner_login="renamed-owner",
                    repository_name="renamed-repo",
                    full_name="renamed-owner/renamed-repo",
                    created_at=datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc),
                    description="Renamed repository for SaaS triage",
                    stargazers_count=42,
                    forks_count=7,
                    pushed_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                )
            ],
        )
        refreshed = session.get(type(existing), 101)

    assert result.inserted_count == 0
    assert result.skipped_count == 1
    assert refreshed is not None
    assert refreshed.owner_login == "renamed-owner"
    assert refreshed.repository_name == "renamed-repo"
    assert refreshed.full_name == "renamed-owner/renamed-repo"
    assert refreshed.repository_description == "Renamed repository for SaaS triage"
    assert refreshed.stargazers_count == 42
    assert refreshed.forks_count == 7
    assert refreshed.pushed_at == datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
    assert refreshed.queue_status is RepositoryQueueStatus.COMPLETED
    assert refreshed.queue_created_at == original_queue_created_at
    assert refreshed.processing_completed_at == original_completed_at
    assert refreshed.status_updated_at == original_status_updated_at


def test_persist_repository_batch_wraps_constraint_failures_with_structured_error(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        with pytest.raises(IntakePersistenceError) as exc_info:
            persist_backfill_batch(
                session,
                [
                    DiscoveredRepository(
                        github_repository_id=202,
                        owner_login="",
                        repository_name="repo-202",
                        full_name="/repo-202",
                        created_at=datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc),
                        stargazers_count=0,
                        forks_count=0,
                        pushed_at=datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc),
                    )
                ],
            )

    error = exc_info.value
    assert error.github_repository_id == 202
    assert error.operation == "upsert"


def test_persist_idea_scout_batch_records_discovery_links(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        search = IdeaSearch(
            idea_text="Open source prediction market tooling",
            search_queries=["prediction market tooling"],
            direction=IdeaSearchDirection.BACKWARD,
        )
        session.add(search)
        session.commit()
        session.refresh(search)

        result = persist_idea_scout_batch(
            session,
            [
                DiscoveredRepository(
                    github_repository_id=303,
                    owner_login="octocat",
                    repository_name="repo-303",
                    full_name="octocat/repo-303",
                    created_at=datetime(2026, 3, 8, 9, 0, tzinfo=timezone.utc),
                    description="Prediction market automation",
                    stargazers_count=12,
                    forks_count=3,
                    pushed_at=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                )
            ],
            idea_search_id=search.id,
        )

        stored_repo = session.get(RepositoryIntake, 303)
        stored_search = session.get(IdeaSearch, search.id)
        discoveries = session.exec(
            select(IdeaSearchDiscovery).where(IdeaSearchDiscovery.idea_search_id == search.id)
        ).all()

    assert result.inserted_count == 1
    assert result.skipped_count == 0
    assert stored_repo is not None
    assert stored_repo.discovery_source is RepositoryDiscoverySource.IDEA_SCOUT
    assert stored_search is not None
    assert stored_search.total_repos_found == 1
    assert len(discoveries) == 1
    assert discoveries[0].github_repository_id == 303
