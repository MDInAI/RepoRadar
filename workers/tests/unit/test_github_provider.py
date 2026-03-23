from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import json
from socket import timeout as SocketTimeout
from urllib.error import HTTPError

import pytest

import agentic_workers.providers.github_provider as github_provider_module
from agentic_workers.providers.github_provider import (
    FirehoseMode,
    GitHubAuthenticationError,
    GitHubFirehoseProvider,
    GitHubPayloadError,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
    RepositoryCommit,
    RepositoryContributor,
    RepositoryFileSnapshot,
    RepositoryMetadata,
    RepositoryPullRequest,
    RepositoryRelease,
    RepositoryTreeEntry,
    UrllibGitHubTransport,
)


class RecordingTransport:
    def __init__(
        self,
        responses: dict[str, object] | list[dict[str, object]],
        *,
        text_responses: str | list[str] | None = None,
    ) -> None:
        if isinstance(responses, dict):
            self.responses = [responses]
        else:
            self.responses = list(responses)
        if text_responses is None:
            self.text_responses: list[str] = []
        elif isinstance(text_responses, str):
            self.text_responses = [text_responses]
        else:
            self.text_responses = list(text_responses)
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "token_label": token_label,
            }
        )
        call_index = len(self.calls) - 1
        if call_index < len(self.responses):
            response = self.responses[call_index]
        else:
            response = self.responses[-1]
        if isinstance(response, Exception):
            raise response
        return response

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "text": True,
                "token_label": token_label,
            }
        )
        call_index = sum(1 for call in self.calls if call.get("text")) - 1
        if call_index < len(self.text_responses):
            response = self.text_responses[call_index]
        else:
            response = self.text_responses[-1]
        if isinstance(response, Exception):
            raise response
        return response


def _repository_payload(
    repository_id: int = 123456,
    *,
    created_at: str = "2026-03-07T00:00:00Z",
    pushed_at: str = "2026-03-08T00:00:00Z",
    description: str | None = "Open source developer tools for SaaS teams",
    stargazers_count: int = 123,
    forks_count: int = 45,
) -> dict[str, object]:
    return {
        "id": repository_id,
        "name": "hello-world",
        "full_name": "octocat/hello-world",
        "created_at": created_at,
        "pushed_at": pushed_at,
        "description": description,
        "stargazers_count": stargazers_count,
        "forks_count": forks_count,
        "owner": {"login": "octocat"},
    }


class ReadmeTransport:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> dict[str, object]:
        raise AssertionError("get_json should not be called in this test")

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> str:
        self.calls.append(
            {"url": url, "headers": headers, "params": params, "token_label": token_label}
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

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


def test_provider_uses_explicit_firehose_anchor_instead_of_current_day() -> None:
    transport = RecordingTransport({"items": [_repository_payload(201)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    provider.discover(
        mode=FirehoseMode.TRENDING,
        anchor_date=date(2026, 2, 20),
        per_page=10,
        page=2,
    )

    assert transport.calls[0]["params"] == {
        "order": "desc",
        "page": "2",
        "per_page": "10",
        "q": "pushed:>=2026-02-20 stars:>=50 archived:false is:public",
        "sort": "stars",
    }


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
    assert repositories[0].description == "Open source developer tools for SaaS teams"
    assert repositories[0].stargazers_count == 123
    assert repositories[0].forks_count == 45
    assert repositories[0].pushed_at == datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)
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
        "q": "created:2026-02-01..2026-02-28 archived:false is:public",
        "sort": "created",
        "order": "desc",
    }
    assert repositories[0].created_at == datetime(2026, 3, 7, 0, 0, tzinfo=timezone.utc)
    assert repositories[0].pushed_at == datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)


def test_provider_logs_warning_when_backfill_per_page_exceeds_github_limit(caplog: pytest.LogCaptureFixture) -> None:
    transport = RecordingTransport({"items": [_repository_payload(repository_id=654321)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    with caplog.at_level("WARNING"):
        provider.discover_backfill(
            window_start_date=date(2026, 2, 1),
            created_before_boundary=date(2026, 3, 1),
            per_page=200,
            page=1,
        )

    assert transport.calls[0]["params"]["per_page"] == "100"
    assert "BACKFILL_PER_PAGE=200 exceeds GitHub's max page size of 100" in caplog.text


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


def test_provider_fetches_readme_with_raw_media_type() -> None:
    transport = ReadmeTransport("# Product\n\nAutomation platform for SaaS teams.")
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token="token",
        today=date(2026, 3, 7),
    )

    readme = provider.get_readme(owner_login="octocat", repository_name="hello-world")

    assert readme.owner_login == "octocat"
    assert readme.repository_name == "hello-world"
    assert "Automation platform" in readme.content
    assert transport.calls[0]["url"] == "https://api.github.com/repos/octocat/hello-world/readme"
    assert transport.calls[0]["headers"] == {
        "Accept": "application/vnd.github.raw+json",
        "Authorization": "Bearer token",
        "User-Agent": "agentic-workflow-analyst",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    assert transport.calls[0]["params"] == {}


def test_provider_surfaces_missing_readme_errors() -> None:
    transport = ReadmeTransport(
        GitHubReadmeNotFoundError("Repository README not found for octocat/hello-world")
    )
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    with pytest.raises(GitHubReadmeNotFoundError):
        provider.get_readme(owner_login="octocat", repository_name="hello-world")


def test_provider_rejects_blank_readme_payload() -> None:
    transport = ReadmeTransport("   \n")
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        today=date(2026, 3, 7),
    )

    with pytest.raises(GitHubPayloadError, match="empty"):
        provider.get_readme(owner_login="octocat", repository_name="hello-world")


def test_transport_raises_rate_limit_error_for_http_429(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        raise HTTPError(
            "https://api.github.com/search/repositories",
            429,
            "Too Many Requests",
            {"Retry-After": "120"},
            BytesIO(b""),
        )

    monkeypatch.setattr(github_provider_module, "urlopen", fake_urlopen)
    transport = UrllibGitHubTransport()

    with pytest.raises(GitHubRateLimitError, match="retry after 120s") as excinfo:
        transport.get_json(
            url="https://api.github.com/search/repositories",
            headers={},
            params={"q": "created:>=2026-03-07"},
        )

    assert excinfo.value.retry_after_seconds == 120


def test_transport_raises_rate_limit_error_for_rate_limit_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_at = int(datetime.now(timezone.utc).timestamp()) + 90

    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        raise HTTPError(
            "https://api.github.com/search/repositories",
            403,
            "Forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset_at)},
            BytesIO(b""),
        )

    monkeypatch.setattr(github_provider_module, "urlopen", fake_urlopen)
    transport = UrllibGitHubTransport()

    with pytest.raises(GitHubRateLimitError, match="status 403") as excinfo:
        transport.get_json(
            url="https://api.github.com/search/repositories",
            headers={},
            params={"q": "created:>=2026-03-07"},
        )

    assert excinfo.value.retry_after_seconds is not None
    assert 1 <= excinfo.value.retry_after_seconds <= 90


def test_transport_writes_shared_github_quota_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class FakeResponse:
        status = 200
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4988",
            "X-RateLimit-Used": "12",
            "X-RateLimit-Reset": "1772870400",
            "X-RateLimit-Resource": "core",
        }

        def read(self) -> bytes:
            return b'{"items": []}'

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(github_provider_module, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    transport = UrllibGitHubTransport(runtime_dir=tmp_path)

    payload = transport.get_json(
        url="https://api.github.com/search/repositories",
        headers={},
        params={"q": "created:>=2026-03-07"},
        token_label="token-1",
    )

    assert payload == {"items": []}
    snapshot = json.loads((tmp_path / "github" / "quota.json").read_text(encoding="utf-8"))
    assert snapshot["provider"] == "github"
    assert snapshot["limit"] == 5000
    assert snapshot["remaining"] == 4988
    assert snapshot["used"] == 12
    assert snapshot["resource"] == "core"
    assert snapshot["last_response_status"] == 200
    assert snapshot["tokens"][0]["label"] == "token-1"
    assert snapshot["tokens"][0]["resource_budgets"][0]["resource"] == "core"


def test_transport_retries_timeout_before_succeeding(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    class FakeResponse:
        status = 200
        headers = {}

        def read(self) -> bytes:
            return b'{"items": []}'

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise SocketTimeout("The read operation timed out")
        return FakeResponse()

    monkeypatch.setattr(github_provider_module, "urlopen", fake_urlopen)
    transport = UrllibGitHubTransport(retry_backoff_seconds=0)

    payload = transport.get_json(
        url="https://api.github.com/search/repositories",
        headers={},
        params={"q": "created:>=2026-03-07"},
    )

    assert payload == {"items": []}
    assert attempts["count"] == 3


def test_transport_raises_provider_error_after_exhausting_timeout_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}

    def fake_urlopen(*_args: object, **_kwargs: object) -> object:
        attempts["count"] += 1
        raise SocketTimeout("The read operation timed out")

    monkeypatch.setattr(github_provider_module, "urlopen", fake_urlopen)
    transport = UrllibGitHubTransport(retry_backoff_seconds=0)

    with pytest.raises(GitHubProviderError, match="The read operation timed out"):
        transport.get_json(
            url="https://api.github.com/search/repositories",
            headers={},
            params={"q": "created:>=2026-03-07"},
        )

    assert attempts["count"] == 3


def test_provider_rotates_across_multiple_github_tokens() -> None:
    transport = RecordingTransport({"items": [_repository_payload(101)]})
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        github_tokens=("token-a", "token-b"),
        today=date(2026, 3, 7),
    )

    provider.discover(mode=FirehoseMode.NEW, per_page=1, page=1)
    provider.discover(mode=FirehoseMode.NEW, per_page=1, page=2)

    assert transport.calls[0]["headers"]["Authorization"] == "Bearer token-a"
    assert transport.calls[0]["token_label"] == "token-1"
    assert transport.calls[1]["headers"]["Authorization"] == "Bearer token-b"
    assert transport.calls[1]["token_label"] == "token-2"


def test_providers_share_token_pool_across_instances(tmp_path) -> None:
    transport_one = RecordingTransport({"items": [_repository_payload(101)]})
    transport_two = RecordingTransport({"items": [_repository_payload(102)]})
    provider_one = GitHubFirehoseProvider(
        transport=transport_one,
        github_token=None,
        github_tokens=("token-a", "token-b"),
        runtime_dir=tmp_path,
        today=date(2026, 3, 7),
    )
    provider_two = GitHubFirehoseProvider(
        transport=transport_two,
        github_token=None,
        github_tokens=("token-a", "token-b"),
        runtime_dir=tmp_path,
        today=date(2026, 3, 7),
    )

    provider_one.discover(mode=FirehoseMode.NEW, per_page=1, page=1)
    provider_two.discover(mode=FirehoseMode.NEW, per_page=1, page=1)

    assert provider_one._token_pool is provider_two._token_pool
    assert transport_one.calls[0]["token_label"] == "token-1"
    assert transport_two.calls[0]["token_label"] == "token-2"


def test_provider_initializes_scheduler_snapshot(tmp_path) -> None:
    GitHubFirehoseProvider(
        transport=RecordingTransport({"items": []}),
        github_token=None,
        github_tokens=("token-a", "token-b"),
        runtime_dir=tmp_path,
        today=date(2026, 3, 7),
    )

    snapshot = json.loads((tmp_path / "github" / "quota.json").read_text(encoding="utf-8"))
    assert snapshot["scheduler"]["configured_tokens"] == 2
    assert snapshot["scheduler"]["search_min_interval_seconds"] == 2.0
    assert snapshot["tokens"][0]["in_flight"] == 0
    assert snapshot["tokens"][0]["next_available_at"] is None


def test_provider_quarantines_unauthorized_token_and_rotates_to_next_search_token() -> None:
    transport = RecordingTransport(
        [
            GitHubAuthenticationError("GitHub request failed with status 401: Unauthorized"),
            {"items": [_repository_payload(201)]},
        ]
    )
    provider = GitHubFirehoseProvider(
        transport=transport,
        github_token=None,
        github_tokens=("token-a", "token-b"),
        today=date(2026, 3, 7),
    )

    repositories = provider.discover(mode=FirehoseMode.NEW, per_page=1, page=1)

    assert len(repositories) == 1
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer token-a"
    assert transport.calls[0]["token_label"] == "token-1"
    assert transport.calls[1]["headers"]["Authorization"] == "Bearer token-b"
    assert transport.calls[1]["token_label"] == "token-2"


def test_provider_rejects_malformed_repository_payloads() -> None:
    transport = RecordingTransport(
        {
            "items": [
                {
                    "id": 123456,
                    "name": "missing-owner",
                    "created_at": "2026-03-07T00:00:00Z",
                    "pushed_at": "2026-03-08T00:00:00Z",
                    "stargazers_count": 123,
                    "forks_count": 45,
                }
            ]
        }
    )
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 7))

    with pytest.raises(GitHubPayloadError, match="owner.login"):
        provider.discover(mode=FirehoseMode.NEW)


def test_provider_rejects_non_string_optional_description() -> None:
    transport = RecordingTransport({"items": [_repository_payload(description=None)]})
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 7))

    repositories = provider.discover(mode=FirehoseMode.NEW)

    assert repositories[0].description is None


def test_provider_fetches_repository_metadata() -> None:
    transport = RecordingTransport(
        {
            "full_name": "octocat/hello-world",
            "default_branch": "main",
            "description": "Automation platform",
            "homepage": "https://example.com",
            "language": "Python",
            "license": {"spdx_id": "MIT"},
            "topics": ["automation", "workflow"],
            "stargazers_count": 321,
            "forks_count": 45,
            "open_issues_count": 9,
            "subscribers_count": 12,
            "created_at": "2026-03-01T00:00:00Z",
            "pushed_at": "2026-03-08T00:00:00Z",
            "updated_at": "2026-03-09T00:00:00Z",
        }
    )
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 9))

    metadata = provider.get_repository_metadata(owner_login="octocat", repository_name="hello-world")

    assert isinstance(metadata, RepositoryMetadata)
    assert metadata.full_name == "octocat/hello-world"
    assert metadata.default_branch == "main"
    assert metadata.license_name == "MIT"
    assert metadata.topics == ["automation", "workflow"]
    assert metadata.open_issues_count == 9


def test_provider_lists_repository_activity_and_tree() -> None:
    transport = RecordingTransport(
        [{"tree": [
            {"path": "package.json", "type": "blob"},
            {"path": ".github/workflows/ci.yml", "type": "blob"},
            {"path": "src/app.ts", "type": "blob"},
            {"path": "src/deep/nested/file.ts", "type": "blob"},
        ]}],
        text_responses=[
            '[{"login":"octocat","contributions":12},{"login":"hubot","contributions":3}]',
            '[{"tag_name":"v1.0.0","published_at":"2026-03-01T00:00:00Z","draft":false,"prerelease":false}]',
            '[{"sha":"abc123","commit":{"committer":{"date":"2026-03-08T00:00:00Z"}}}]',
            '[{"number":7,"state":"closed","merged_at":"2026-03-07T00:00:00Z","created_at":"2026-03-05T00:00:00Z","closed_at":"2026-03-07T00:00:00Z"}]',
            '[{"number":9,"state":"open","created_at":"2026-03-06T00:00:00Z","updated_at":"2026-03-08T00:00:00Z"}]',
        ],
    )
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 9))

    contributors = provider.list_contributors(owner_login="octocat", repository_name="hello-world", limit=5)
    releases = provider.list_releases(owner_login="octocat", repository_name="hello-world", limit=10)
    commits = provider.list_recent_commits(owner_login="octocat", repository_name="hello-world", limit=10)
    pulls = provider.list_recent_pull_requests(owner_login="octocat", repository_name="hello-world", limit=10)
    issues = provider.list_recent_issues(owner_login="octocat", repository_name="hello-world", limit=10)
    tree = provider.get_repository_tree(owner_login="octocat", repository_name="hello-world", ref="main", depth_limit=2)

    assert contributors == [
        RepositoryContributor(login="octocat", contributions=12),
        RepositoryContributor(login="hubot", contributions=3),
    ]
    assert releases == [
        RepositoryRelease(
            tag_name="v1.0.0",
            published_at=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
            draft=False,
            prerelease=False,
        )
    ]
    assert commits == [RepositoryCommit(sha="abc123", committed_at=datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc))]
    assert pulls == [
        RepositoryPullRequest(
            number=7,
            merged_at=datetime(2026, 3, 7, 0, 0, tzinfo=timezone.utc),
            state="closed",
            created_at=datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 3, 7, 0, 0, tzinfo=timezone.utc),
        )
    ]
    assert len(issues) == 1
    assert tree == [
        RepositoryTreeEntry(path="package.json", entry_type="blob"),
        RepositoryTreeEntry(path=".github/workflows/ci.yml", entry_type="blob"),
        RepositoryTreeEntry(path="src/app.ts", entry_type="blob"),
    ]


def test_provider_fetches_optional_file_contents() -> None:
    transport = ReadmeTransport('{"name":"hello"}')
    provider = GitHubFirehoseProvider(transport=transport, github_token=None, today=date(2026, 3, 9))

    file_snapshot = provider.get_file_contents(
        owner_login="octocat",
        repository_name="hello-world",
        path="package.json",
    )

    assert file_snapshot == RepositoryFileSnapshot(
        path="package.json",
        content='{"name":"hello"}',
        fetched_at=file_snapshot.fetched_at,  # type: ignore[arg-type]
        source_url="https://api.github.com/repos/octocat/hello-world/contents/package.json",
    )
