from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.repository import (
    IdeaSearch,
    IdeaSearchDiscovery,
    IdeaSearchProgress,
    RepositoryIntake,
)


def _enum_to_str(value):
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class IdeaSearchRecord:
    id: int
    idea_text: str
    search_queries: list[str]
    direction: str
    status: str
    obsession_context_id: int | None
    total_repos_found: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class IdeaSearchProgressRecord:
    id: int
    idea_search_id: int
    query_index: int
    window_start_date: object  # date
    created_before_boundary: object  # date
    exhausted: bool
    resume_required: bool
    next_page: int
    pages_processed_in_run: int
    last_checkpointed_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class DiscoveredRepoRecord:
    github_repository_id: int
    full_name: str
    description: str | None
    stargazers_count: int
    discovered_at: datetime


class IdeaScoutRepository:
    def __init__(self, session: Session):
        self._session = session

    def _to_record(self, s: IdeaSearch) -> IdeaSearchRecord:
        return IdeaSearchRecord(
            id=s.id,
            idea_text=s.idea_text,
            search_queries=s.search_queries or [],
            direction=_enum_to_str(s.direction),
            status=_enum_to_str(s.status),
            obsession_context_id=s.obsession_context_id,
            total_repos_found=s.total_repos_found,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    def create_search(
        self,
        idea_text: str,
        search_queries: list[str],
        direction: str,
        obsession_context_id: int | None = None,
    ) -> IdeaSearchRecord:
        search = IdeaSearch(
            idea_text=idea_text,
            search_queries=search_queries,
            direction=direction,
            obsession_context_id=obsession_context_id,
        )
        self._session.add(search)
        self._session.flush()
        return self._to_record(search)

    def get_search(self, search_id: int) -> IdeaSearchRecord | None:
        search = self._session.get(IdeaSearch, search_id)
        if not search:
            return None
        return self._to_record(search)

    def list_searches(
        self,
        status: str | None = None,
        direction: str | None = None,
    ) -> list[IdeaSearchRecord]:
        stmt = select(IdeaSearch)
        if status is not None:
            stmt = stmt.where(IdeaSearch.status == status)
        if direction is not None:
            stmt = stmt.where(IdeaSearch.direction == direction)
        stmt = stmt.order_by(IdeaSearch.created_at.desc())
        searches = self._session.execute(stmt).scalars().all()
        return [self._to_record(s) for s in searches]

    def update_search_status(self, search_id: int, status: str) -> IdeaSearchRecord:
        search = self._session.get(IdeaSearch, search_id)
        if not search:
            from app.core.errors import AppError
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        search.status = status
        search.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return self._to_record(search)

    def update_search_queries(self, search_id: int, queries: list[str]) -> IdeaSearchRecord:
        search = self._session.get(IdeaSearch, search_id)
        if not search:
            from app.core.errors import AppError
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        search.search_queries = queries
        search.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return self._to_record(search)

    def get_progress(self, idea_search_id: int) -> list[IdeaSearchProgressRecord]:
        stmt = (
            select(IdeaSearchProgress)
            .where(IdeaSearchProgress.idea_search_id == idea_search_id)
            .order_by(IdeaSearchProgress.query_index)
        )
        records = self._session.execute(stmt).scalars().all()
        return [
            IdeaSearchProgressRecord(
                id=r.id,
                idea_search_id=r.idea_search_id,
                query_index=r.query_index,
                window_start_date=r.window_start_date,
                created_before_boundary=r.created_before_boundary,
                exhausted=r.exhausted,
                resume_required=r.resume_required,
                next_page=r.next_page,
                pages_processed_in_run=r.pages_processed_in_run,
                last_checkpointed_at=r.last_checkpointed_at,
                updated_at=r.updated_at,
            )
            for r in records
        ]

    def list_discoveries(
        self,
        idea_search_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoveredRepoRecord]:
        stmt = (
            select(IdeaSearchDiscovery, RepositoryIntake)
            .join(RepositoryIntake, IdeaSearchDiscovery.github_repository_id == RepositoryIntake.github_repository_id)
            .where(IdeaSearchDiscovery.idea_search_id == idea_search_id)
            .order_by(IdeaSearchDiscovery.discovered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = self._session.execute(stmt).all()
        return [
            DiscoveredRepoRecord(
                github_repository_id=disc.github_repository_id,
                full_name=repo.full_name,
                description=repo.repository_description,
                stargazers_count=repo.stargazers_count,
                discovered_at=disc.discovered_at,
            )
            for disc, repo in rows
        ]

    def get_discovery_count(self, idea_search_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(IdeaSearchDiscovery)
            .where(IdeaSearchDiscovery.idea_search_id == idea_search_id)
        )
        return self._session.execute(stmt).scalar_one()
