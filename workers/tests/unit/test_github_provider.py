from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import agentic_workers.providers.github_provider as github_provider_module
from agentic_workers.providers.github_provider import (
    FirehoseMode,
    GitHubFirehoseProvider,
    GitHubPayloadError,
)


class RecordingTransport:
    def __init__(self, responses: dict[str, object] | list[dict[str, object]]) -> None:
        if isinstance(responses, dict):
            self.responses = [responses]
        else:
            self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
            }
        )
        call_index = len(self.calls) - 1
        if call_index < len(self.responses):
            return self.responses[call_index]
        return self.responses[-1]


def _repository_payload(
    repository_id: int = 123456,
    *,
    created_at: str = "2026-03-07T00:00:00Z",
) -> dict[str, object]:
    return {
        "id": repository_id,
        "name": "hello-world",
        "full_name": "octocat/hello-world",
        "created_at": created_at,
        "owner": {"login": "octocat"},
    }



def test_provider_builds_new_repository_query_with_api_sort_and_single_request() -> None:
    transport = RecordingTransport(
        {"items": [_repository_payload(101), _repository_payload(102)]}
    )
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token="test-token",
        today=date(2026, 3, 7),
    )

    repositories = provider.discover(mode=FirehoseMode.NEW, per_page=2, page=1)

    assert len(repositories) == 2
    assert all(repository.firehose_discovery_mode is FirehoseMode.NEW for repository in repositories)
    # Exactly one API call — no multi-page sampling
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://api.github.com/search/repositories"
    assert call["headers"] == {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer test-token",
        "User-Agent": "agentic-workflow-firehose",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    assert call["params"] == {
        "page": "1",
        "per_page": "2",
        "q": "created:>=2026-03-06 archived:false is:public",
        "sort": "created",
        "order": "desc",
    }


def test_provider_passes_page_parameter_through_for_new_mode() -> None:
    transport = RecordingTransport({"items": [_repository_payload(200)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    provider.discover(mode=FirehoseMode.NEW, per_page=10, page=3)

    assert len(transport.calls) == 1
    assert transport.calls[0]["params"]["page"] == "3"
    assert transport.calls[0]["params"]["sort"] == "created"
    assert transport.calls[0]["params"]["order"] == "desc"


def test_provider_builds_trending_query_without_auth_header() -> None:
    transport = RecordingTransport({"items": [_repository_payload(repository_id=987654)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    repositories = provider.discover(mode=FirehoseMode.TRENDING, per_page=50, page=1)

    assert len(repositories) == 1
    assert repositories[0].github_repository_id == 987654
    assert repositories[0].firehose_discovery_mode is FirehoseMode.TRENDING

    call = transport.calls[0]
    assert call["headers"] == {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentic-workflow-firehose",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    assert call["params"] == {
        "order": "desc",
        "page": "1",
        "per_page": "50",
        "q": "pushed:>=2026-02-28 stars:>=50 archived:false is:public",
        "sort": "stars",
    }


def test_provider_builds_backfill_query_with_created_window_and_backfill_headers() -> None:
    transport = RecordingTransport({"items": [_repository_payload(repository_id=345678)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token="test-token",
        today=date(2026, 3, 7),
    )

    repositories = provider.discover_backfill(
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        per_page=75,
        page=2,
    )

    assert len(repositories) == 1
    assert repositories[0].github_repository_id == 345678
    assert repositories[0].firehose_discovery_mode is None

    call = transport.calls[0]
    assert call["headers"] == {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer test-token",
        "User-Agent": "agentic-workflow-backfill",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    assert call["params"] == {
        "page": "2",
        "per_page": "75",
        "q": "created:>=2026-02-01 created:<2026-03-01T00:00:00Z archived:false is:public",
        "sort": "created",
        "order": "desc",
    }
    assert repositories[0].created_at == datetime(2026, 3, 7, 0, 0, tzinfo=timezone.utc)


def test_provider_builds_backfill_query_with_exact_resume_cursor() -> None:
    transport = RecordingTransport({"items": [_repository_payload(repository_id=456789)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    provider.discover_backfill(
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
        created_before_cursor=datetime(2026, 2, 15, 12, 30, tzinfo=timezone.utc),
        per_page=25,
        page=1,
    )

    assert transport.calls[0]["params"]["q"] == (
        "created:>=2026-02-01 created:<=2026-02-15T12:30:00Z archived:false is:public"
    )


def test_provider_defaults_today_from_utc_clock(monkeypatch) -> None:
    transport = RecordingTransport({"items": [_repository_payload(repository_id=567890)]})
    monkeypatch.setattr(github_provider_module, "_utc_today", lambda: date(2026, 3, 8))

    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
    )

    provider.discover(mode=FirehoseMode.NEW, per_page=10, page=1)

    assert transport.calls[0]["params"]["q"] == "created:>=2026-03-07 archived:false is:public"


def test_provider_rejects_malformed_repository_payloads() -> None:
    transport = RecordingTransport(
        {
            "items": [
                {
                    "id": 123456,
                    "name": "missing-owner",
                    "created_at": "2026-03-07T00:00:00Z",
                }
            ]
        }
    )
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 7))

    with pytest.raises(GitHubPayloadError, match="owner.login"):
        provider.discover(mode=FirehoseMode.NEW)
