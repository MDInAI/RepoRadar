"""Persist IdeaScout-discovered repositories and track discovery linkage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from agentic_workers.providers.github_provider import DiscoveredRepository
from agentic_workers.storage.backend_models import (
    IdeaSearch,
    IdeaSearchDiscovery,
    RepositoryDiscoverySource,
)
from agentic_workers.storage.repository_intake import (
    IntakePersistenceResult,
    persist_repository_batch,
)


def persist_idea_scout_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    idea_search_id: int,
    query_index: int = 0,
    query_text: str = "",
    commit: bool = True,
) -> IntakePersistenceResult:
    """Persist discovered repos and link them to the originating IdeaSearch."""
    result = persist_repository_batch(
        session,
        repositories,
        discovery_source=RepositoryDiscoverySource.IDEA_SCOUT,
        firehose_mode=None,
        commit=False,
    )

    # Record discovery linkage — on conflict do nothing so the first query
    # that finds a repo wins (query_index/query_text reflect the original discoverer).
    now = datetime.now(timezone.utc)
    for repo in repositories:
        stmt = (
            sqlite_insert(IdeaSearchDiscovery)
            .values(
                idea_search_id=idea_search_id,
                github_repository_id=repo.github_repository_id,
                discovered_at=now,
                query_index=query_index,
                query_text=query_text,
            )
            .on_conflict_do_nothing(
                index_elements=["idea_search_id", "github_repository_id"],
            )
        )
        session.execute(stmt)

    # Update the running total on IdeaSearch
    search = session.get(IdeaSearch, idea_search_id)
    if search is not None:
        search.total_repos_found = (search.total_repos_found or 0) + result.inserted_count
        search.updated_at = now

    if commit:
        session.commit()

    return result
