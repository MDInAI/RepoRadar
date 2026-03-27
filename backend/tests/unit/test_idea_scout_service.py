from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.errors import AppError
from app.services import idea_scout_service
from app.services.idea_scout_service import IdeaScoutService


@dataclass
class _StoredSearch:
    id: int
    idea_text: str
    search_queries: list[str]
    direction: str
    obsession_context_id: int | None


class _FakeIdeaScoutRepository:
    def __init__(self) -> None:
        self.created: _StoredSearch | None = None

    def create_search(
        self,
        *,
        idea_text: str,
        search_queries: list[str],
        direction: str,
        obsession_context_id: int | None = None,
    ) -> _StoredSearch:
        self.created = _StoredSearch(
            id=1,
            idea_text=idea_text,
            search_queries=search_queries,
            direction=direction,
            obsession_context_id=obsession_context_id,
        )
        return self.created


def test_create_search_uses_heuristic_builder_when_analyst_is_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeIdeaScoutRepository()
    service = IdeaScoutService(repo)

    monkeypatch.setattr(idea_scout_service.settings, "ANALYST_PROVIDER", "heuristic")
    monkeypatch.setattr(
        idea_scout_service,
        "generate_search_queries",
        lambda idea_text: [f'"{idea_text}" archived:false is:public'],
    )

    created = service.create_search("agent memory for support teams")

    assert created.search_queries == ['"agent memory for support teams" archived:false is:public']


def test_create_search_uses_worker_query_builder_when_analyst_uses_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeIdeaScoutRepository()
    service = IdeaScoutService(repo)

    class _Result:
        returncode = 0
        stdout = '{"queries": ["agent memory archived:false is:public"]}'
        stderr = ""

    monkeypatch.setattr(idea_scout_service.settings, "ANALYST_PROVIDER", "llm")
    monkeypatch.setattr(idea_scout_service.subprocess, "run", lambda *args, **kwargs: _Result())

    created = service.create_search("agent memory for support teams")

    assert created.search_queries == ["agent memory archived:false is:public"]


def test_create_search_raises_clear_error_when_worker_query_builder_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _FakeIdeaScoutRepository()
    service = IdeaScoutService(repo)

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "analyst model unavailable"

    monkeypatch.setattr(idea_scout_service.settings, "ANALYST_PROVIDER", "gemini")
    monkeypatch.setattr(idea_scout_service.subprocess, "run", lambda *args, **kwargs: _Result())

    with pytest.raises(AppError, match="analyst model unavailable"):
        service.create_search("agent memory for support teams")
