from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Workers' query builder is reused by the backend service
WORKERS_ROOT = Path(__file__).resolve().parents[3] / "workers"
WORKERS_PYTHON = WORKERS_ROOT / ".venv" / "bin" / "python"
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from agentic_workers.jobs.idea_query_builder import generate_search_queries  # noqa: E402

from app.core.errors import AppError
from app.core.config import settings
from app.repositories.idea_scout_repository import (
    IdeaScoutRepository,
    IdeaSearchRecord,
    IdeaSearchProgressRecord,
    DiscoveredRepoRecord,
)


class IdeaScoutService:
    def __init__(self, idea_scout_repo: IdeaScoutRepository):
        self._repo = idea_scout_repo

    def _generate_queries(self, idea_text: str) -> list[str]:
        if settings.ANALYST_PROVIDER == "heuristic":
            return generate_search_queries(idea_text)

        env = os.environ.copy()
        env["ANALYST_PROVIDER"] = settings.ANALYST_PROVIDER
        env["ANALYST_MODEL_NAME"] = settings.ANALYST_MODEL_NAME
        env["GEMINI_BASE_URL"] = settings.GEMINI_BASE_URL
        env["GEMINI_MODEL_NAME"] = settings.GEMINI_MODEL_NAME

        if settings.ANTHROPIC_API_KEY:
            env["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY.get_secret_value()
        if settings.GEMINI_API_KEY:
            env["GEMINI_API_KEY"] = settings.GEMINI_API_KEY.get_secret_value()
        if settings.GEMINI_API_KEYS:
            env["GEMINI_API_KEYS"] = json.dumps(list(settings.GEMINI_API_KEYS))

        try:
            result = subprocess.run(
                [
                    str(WORKERS_PYTHON),
                    "-m",
                    "agentic_workers.jobs.idea_query_builder",
                    "--idea-text",
                    idea_text,
                ],
                cwd=WORKERS_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AppError(
                message="Scout LLM query builder is unavailable because the worker Python runtime was not found.",
                code="idea_query_builder_unavailable",
                status_code=500,
                details={"worker_python": str(WORKERS_PYTHON)},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AppError(
                message="Scout query generation timed out while waiting for the analyst model.",
                code="idea_query_builder_timeout",
                status_code=504,
            ) from exc

        if result.returncode != 0:
            error_message = result.stderr.strip() or "Scout query generation failed."
            raise AppError(
                message=error_message,
                code="idea_query_builder_failed",
                status_code=502,
            )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AppError(
                message="Scout query generation returned invalid JSON.",
                code="idea_query_builder_invalid_payload",
                status_code=502,
            ) from exc

        raw_queries = payload.get("queries")
        if not isinstance(raw_queries, list) or not raw_queries:
            raise AppError(
                message="Scout query generation returned no usable queries.",
                code="idea_query_builder_empty",
                status_code=502,
            )

        queries = [str(query).strip() for query in raw_queries if str(query).strip()]
        if not queries:
            raise AppError(
                message="Scout query generation returned no usable queries.",
                code="idea_query_builder_empty",
                status_code=502,
            )
        return queries

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

        queries = self._generate_queries(idea_text.strip())
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

    def set_analyst_enabled(self, search_id: int, enabled: bool) -> IdeaSearchRecord:
        search = self._repo.get_search(search_id)
        if not search:
            raise AppError(
                message=f"IdeaSearch {search_id} not found",
                code="idea_search_not_found",
                status_code=404,
            )
        return self._repo.set_analyst_enabled(search_id, enabled)

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
