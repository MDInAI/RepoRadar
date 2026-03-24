from __future__ import annotations

import sys
from pathlib import Path

# Workers' query builder is reused by the backend service
WORKERS_ROOT = Path(__file__).resolve().parents[3] / "workers"
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from agentic_workers.jobs.idea_query_builder import generate_search_queries  # noqa: E402

from app.core.errors import AppError
from app.repositories.idea_scout_repository import (
    IdeaScoutRepository,
    IdeaSearchRecord,
    IdeaSearchProgressRecord,
    DiscoveredRepoRecord,
)


class IdeaScoutService:
    def __init__(self, idea_scout_repo: IdeaScoutRepository):
        self._repo = idea_scout_repo

    def create_search(
        self,
        idea_text: str,
        direction: str = "backward",
        obsession_context_id: int | None = None,
    ) -> IdeaSearchRecord:
        if not idea_text or not idea_text.strip():
            raise AppError(
                message="idea_text must be non-empty",
                code="invalid_input",
                status_code=400,
            )
        if direction not in ("backward", "forward"):
            raise AppError(
                message="direction must be 'backward' or 'forward'",
                code="invalid_input",
                status_code=400,
            )

        queries = generate_search_queries(idea_text.strip())
        return self._repo.create_search(
            idea_text=idea_text.strip(),
            search_queries=queries,
            direction=direction,
            obsession_context_id=obsession_context_id,
        )

    def list_searches(
        self,
        status: str | None = None,
        direction: str | None = None,
    ) -> list[IdeaSearchRecord]:
        return self._repo.list_searches(status=status, direction=direction)

    def get_search_detail(
        self,
        search_id: int,
    ) -> tuple[IdeaSearchRecord, list[IdeaSearchProgressRecord], int]:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        progress = self._repo.get_progress(search_id)
        discovery_count = self._repo.get_discovery_count(search_id)
        return search, progress, discovery_count

    def pause_search(self, search_id: int) -> IdeaSearchRecord:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        if search.status != "active":
            raise AppError(
                message=f"Cannot pause search in '{search.status}' state",
                code="invalid_state_transition",
                status_code=409,
            )
        return self._repo.update_search_status(search_id, "paused")

    def resume_search(self, search_id: int) -> IdeaSearchRecord:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        if search.status != "paused":
            raise AppError(
                message=f"Cannot resume search in '{search.status}' state",
                code="invalid_state_transition",
                status_code=409,
            )
        return self._repo.update_search_status(search_id, "active")

    def cancel_search(self, search_id: int) -> IdeaSearchRecord:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        if search.status in ("completed", "cancelled"):
            raise AppError(
                message=f"Cannot cancel search in '{search.status}' state",
                code="invalid_state_transition",
                status_code=409,
            )
        return self._repo.update_search_status(search_id, "cancelled")

    def update_search_queries(
        self,
        search_id: int,
        queries: list[str],
    ) -> IdeaSearchRecord:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        if not queries:
            raise AppError(
                message="queries must be non-empty",
                code="invalid_input",
                status_code=400,
            )
        return self._repo.update_search_queries(search_id, queries)

    def list_discoveries(
        self,
        search_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiscoveredRepoRecord]:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        return self._repo.list_discoveries(search_id, limit=limit, offset=offset)
