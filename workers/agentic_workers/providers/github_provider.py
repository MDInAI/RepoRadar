from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from enum import StrEnum
import json
import logging
from pathlib import Path
from socket import timeout as SocketTimeout
import threading
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentic_workers.storage.github_quota_snapshots import (
    initialize_github_quota_snapshot,
    write_github_quota_snapshot,
    write_github_scheduler_snapshot,
)


logger = logging.getLogger(__name__)
_TOKEN_POOL_REGISTRY_LOCK = threading.Lock()
_TOKEN_POOL_REGISTRY: dict[tuple[tuple[str | None, ...], str | None, float, float], "GitHubTokenPool"] = {}
_UNAUTHORIZED_TOKEN_COOLDOWN = timedelta(hours=12)


@dataclass(frozen=True, slots=True)
class GitHubQuotaObservation:
    token_label: str | None
    captured_at: datetime
    status_code: int | None
    request_url: str | None
    resource: str | None
    limit: int | None
    remaining: int | None
    used: int | None
    reset_at: datetime | None
    retry_after_seconds: int | None
    exhausted: bool | None


@dataclass(frozen=True, slots=True)
class GitHubTokenSelection:
    label: str
    token: str | None


@dataclass(slots=True)
class GitHubTokenBudgetState:
    label: str
    token: str | None
    last_used_at: datetime | None = None
    cooldown_until: datetime | None = None
    next_available_at: datetime | None = None
    in_flight: int = 0
    resource_observations: dict[str, GitHubQuotaObservation] = field(default_factory=dict)

    def observation_for(self, resource: str | None) -> GitHubQuotaObservation | None:
        if resource and resource in self.resource_observations:
            return self.resource_observations[resource]
        if self.resource_observations:
            return max(
                self.resource_observations.values(),
                key=lambda observation: observation.captured_at,
            )
        return None


class GitHubTokenPool:
    def __init__(
        self,
        tokens: list[str | None],
        *,
        runtime_dir: Path | None = None,
        core_min_interval_seconds: float = 1.0,
        search_min_interval_seconds: float = 2.0,
    ) -> None:
        normalized = list(tokens) if tokens else [None]
        if not normalized:
            normalized = [None]
        self._states = [
            GitHubTokenBudgetState(label=f"token-{index + 1}", token=token)
            for index, token in enumerate(normalized)
        ]
        self._runtime_dir = runtime_dir
        self._core_min_interval_seconds = max(core_min_interval_seconds, 0.0)
        self._search_min_interval_seconds = max(search_min_interval_seconds, 0.0)
        self._condition = threading.Condition()
        self._write_scheduler_snapshot_locked()

    @contextmanager
    def lease(self, preferred_resource: str | None):
        selection = self.acquire(preferred_resource)
        try:
            yield selection
        finally:
            self.release(selection.label)

    def acquire(self, preferred_resource: str | None, *, max_wait_seconds: float = 120.0) -> GitHubTokenSelection:
        resource = preferred_resource or "core"
        deadline = datetime.now(timezone.utc) + timedelta(seconds=max_wait_seconds)
        with self._condition:
            while True:
                now = datetime.now(timezone.utc)
                selected = self._select_available_state_locked(resource, now)
                if selected is not None:
                    selected.last_used_at = now
                    selected.in_flight += 1
                    selected.next_available_at = now + timedelta(
                        seconds=self._resource_min_interval_seconds(resource)
                    )
                    self._write_scheduler_snapshot_locked()
                    return GitHubTokenSelection(label=selected.label, token=selected.token)

                if now >= deadline:
                    raise GitHubRateLimitError(
                        status_code=429,
                        retry_after_seconds=60,
                        token_label=None,
                        resource=resource,
                    )
                wait_secs = min(self._next_wait_seconds_locked(now), (deadline - now).total_seconds())
                self._condition.wait(timeout=max(wait_secs, 0.05))

    def observe(self, observation: GitHubQuotaObservation) -> None:
        if not observation.token_label:
            return
        with self._condition:
            state = self._state_by_label(observation.token_label)
            if state is None:
                return
            if observation.resource:
                state.resource_observations[observation.resource] = observation
            # Only set cooldown when actually rate-limited (429 or exhausted),
            # not on every response that carries X-RateLimit-Reset.
            is_rate_limited = (
                observation.status_code == 429
                or observation.exhausted is True
            )
            if is_rate_limited and observation.retry_after_seconds is not None and observation.retry_after_seconds > 0:
                state.cooldown_until = observation.captured_at + timedelta(seconds=observation.retry_after_seconds)
            elif observation.exhausted is False:
                state.cooldown_until = None
            self._write_scheduler_snapshot_locked()
            self._condition.notify_all()

    def mark_rate_limited(
        self,
        *,
        token_label: str | None,
        resource: str | None,
        retry_after_seconds: int | None,
    ) -> None:
        if not token_label:
            return
        with self._condition:
            state = self._state_by_label(token_label)
            if state is None:
                return
            if retry_after_seconds is not None and retry_after_seconds > 0:
                state.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
            observation = state.observation_for(resource)
            if observation is not None:
                state.resource_observations[resource or "unknown"] = GitHubQuotaObservation(
                    token_label=observation.token_label,
                    captured_at=datetime.now(timezone.utc),
                    status_code=observation.status_code,
                    request_url=observation.request_url,
                    resource=resource or observation.resource,
                    limit=observation.limit,
                    remaining=0 if observation.remaining is not None else None,
                    used=observation.used,
                    reset_at=observation.reset_at,
                    retry_after_seconds=retry_after_seconds,
                    exhausted=True,
                )
            self._write_scheduler_snapshot_locked()
            self._condition.notify_all()

    def mark_unauthorized(
        self,
        *,
        token_label: str | None,
        resource: str | None,
    ) -> None:
        if not token_label:
            return
        with self._condition:
            state = self._state_by_label(token_label)
            if state is None:
                return
            now = datetime.now(timezone.utc)
            cooldown_until = now + _UNAUTHORIZED_TOKEN_COOLDOWN
            state.cooldown_until = cooldown_until
            state.next_available_at = cooldown_until
            state.resource_observations[resource or "unknown"] = GitHubQuotaObservation(
                token_label=token_label,
                captured_at=now,
                status_code=401,
                request_url=None,
                resource=resource,
                limit=None,
                remaining=None,
                used=None,
                reset_at=cooldown_until,
                retry_after_seconds=int(_UNAUTHORIZED_TOKEN_COOLDOWN.total_seconds()),
                exhausted=True,
            )
            self._write_scheduler_snapshot_locked()
            self._condition.notify_all()

    def release(self, token_label: str) -> None:
        with self._condition:
            state = self._state_by_label(token_label)
            if state is None:
                return
            state.in_flight = max(0, state.in_flight - 1)
            self._write_scheduler_snapshot_locked()
            self._condition.notify_all()

    def token_count(self) -> int:
        return len(self._states)

    def labels(self) -> tuple[str, ...]:
        return tuple(state.label for state in self._states)

    def token_for_label(self, label: str) -> str | None:
        state = self._state_by_label(label)
        return state.token if state is not None else None

    def _state_by_label(self, label: str) -> GitHubTokenBudgetState | None:
        for state in self._states:
            if state.label == label:
                return state
        return None

    def _resource_min_interval_seconds(self, resource: str | None) -> float:
        if resource == "search":
            return self._search_min_interval_seconds
        return self._core_min_interval_seconds

    def _select_available_state_locked(
        self,
        resource: str,
        now: datetime,
    ) -> GitHubTokenBudgetState | None:
        candidates = [
            state
            for state in self._states
            if self._state_ready_for_use(state, resource, now)
        ]
        if not candidates:
            return None

        unknown_budget_states = [
            state for state in candidates if state.observation_for(resource) is None
        ]
        if unknown_budget_states:
            return min(
                unknown_budget_states,
                key=lambda state: (_last_used_sort_key(state.last_used_at), state.label),
            )

        return max(
            candidates,
            key=lambda state: (
                _observation_remaining(state.observation_for(resource)),
                -state.in_flight,
                -_last_used_sort_key(state.last_used_at),
            ),
        )

    @staticmethod
    def _state_ready_for_use(
        state: GitHubTokenBudgetState,
        resource: str,
        now: datetime,
    ) -> bool:
        if state.cooldown_until is not None and state.cooldown_until > now:
            return False
        if state.in_flight > 0:
            return False
        if state.next_available_at is not None and state.next_available_at > now:
            return False
        observation = state.observation_for(resource)
        if observation is None:
            return True
        if not observation.exhausted:
            return True
        if observation.reset_at is None:
            return False
        return observation.reset_at <= now

    def _next_wait_seconds_locked(self, now: datetime) -> float:
        waits: list[float] = []
        for state in self._states:
            target = now
            if state.cooldown_until is not None and state.cooldown_until > target:
                target = state.cooldown_until
            if state.next_available_at is not None and state.next_available_at > target:
                target = state.next_available_at
            latest_observation = state.observation_for("search") or state.observation_for("core")
            if (
                latest_observation is not None
                and latest_observation.exhausted
                and latest_observation.reset_at is not None
                and latest_observation.reset_at > target
            ):
                target = latest_observation.reset_at
            waits.append(max((target - now).total_seconds(), 0.05))
        return min(waits, default=0.05)

    def _write_scheduler_snapshot_locked(self) -> None:
        if self._runtime_dir is None:
            return
        write_github_scheduler_snapshot(
            runtime_dir=self._runtime_dir,
            scheduler={
                "configured_tokens": len(self._states),
                "active_requests": sum(state.in_flight for state in self._states),
                "core_min_interval_seconds": self._core_min_interval_seconds,
                "search_min_interval_seconds": self._search_min_interval_seconds,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
            tokens=[
                {
                    "label": state.label,
                    "last_used_at": state.last_used_at.isoformat() if state.last_used_at else None,
                    "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None,
                    "next_available_at": state.next_available_at.isoformat() if state.next_available_at else None,
                    "in_flight": state.in_flight,
                }
                for state in self._states
            ],
        )


class FirehoseMode(StrEnum):
    NEW = "new"
    TRENDING = "trending"


@dataclass(frozen=True, slots=True)
class DiscoveredRepository:
    github_repository_id: int
    owner_login: str
    repository_name: str
    full_name: str
    created_at: datetime
    description: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    pushed_at: datetime | None = None
    firehose_discovery_mode: FirehoseMode | None = None


@dataclass(frozen=True, slots=True)
class RepositoryReadme:
    owner_login: str
    repository_name: str
    content: str
    fetched_at: datetime
    source_url: str


@dataclass(frozen=True, slots=True)
class RepositoryMetadata:
    owner_login: str
    repository_name: str
    full_name: str
    default_branch: str | None
    description: str | None
    homepage: str | None
    primary_language: str | None
    license_name: str | None
    topics: list[str]
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    subscribers_count: int
    created_at: datetime | None
    pushed_at: datetime | None
    updated_at: datetime | None
    source_url: str
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryContributor:
    login: str
    contributions: int


@dataclass(frozen=True, slots=True)
class RepositoryRelease:
    tag_name: str
    published_at: datetime | None
    draft: bool
    prerelease: bool


@dataclass(frozen=True, slots=True)
class RepositoryCommit:
    sha: str
    committed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepositoryPullRequest:
    number: int
    merged_at: datetime | None
    state: str
    created_at: datetime | None
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepositoryIssue:
    number: int
    state: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RepositoryTreeEntry:
    path: str
    entry_type: str


@dataclass(frozen=True, slots=True)
class RepositoryFileSnapshot:
    path: str
    content: str
    fetched_at: datetime
    source_url: str


class GitHubProviderError(RuntimeError):
    pass


class GitHubAuthenticationError(GitHubProviderError):
    pass


class GitHubPayloadError(GitHubProviderError):
    pass


class GitHubReadmeNotFoundError(GitHubProviderError):
    pass


class GitHubRateLimitError(GitHubProviderError):
    def __init__(
        self,
        *,
        status_code: int,
        retry_after_seconds: int | None = None,
        token_label: str | None = None,
        resource: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.token_label = token_label
        self.resource = resource
        message = f"GitHub rate limit exceeded with status {status_code}"
        if retry_after_seconds is not None:
            message = f"{message}; retry after {retry_after_seconds}s"
        super().__init__(message)


class GitHubTransport(Protocol):
    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> dict[str, object]: ...

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> str: ...


class UrllibGitHubTransport:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_retry_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        runtime_dir: Path | None = None,
        quota_observer: Callable[[GitHubQuotaObservation], None] | None = None,
        token_labels: tuple[str, ...] | list[str] = (),
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retry_attempts = max(1, int(max_retry_attempts))
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.runtime_dir = runtime_dir
        self.quota_observer = quota_observer
        self.token_labels = tuple(label for label in token_labels if isinstance(label, str) and label.strip())

    def _sleep_before_retry(self, attempt: int) -> None:
        if attempt >= self.max_retry_attempts or self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * attempt)

    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> dict[str, object]:
        request = Request(f"{url}?{urlencode(params)}", headers=headers)
        for attempt in range(1, self.max_retry_attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    self._record_quota_snapshot(
                        status_code=getattr(response, "status", None),
                        headers=response.headers,
                        token_label=token_label,
                        request_url=request.full_url,
                    )
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                self._record_quota_snapshot(
                    status_code=exc.code,
                    headers=exc.headers,
                    token_label=token_label,
                    request_url=request.full_url,
                )
                if _is_rate_limited_response(exc):
                    raise GitHubRateLimitError(
                        status_code=exc.code,
                        retry_after_seconds=_parse_retry_after_seconds(exc.headers),
                        token_label=token_label,
                        resource=_parse_rate_limit_resource(exc.headers),
                    ) from exc
                if exc.code == 401:
                    raise GitHubAuthenticationError(
                        f"GitHub request failed with status {exc.code}: {exc.reason}"
                    ) from exc
                raise GitHubProviderError(
                    f"GitHub request failed with status {exc.code}: {exc.reason}"
                ) from exc
            except (URLError, TimeoutError, SocketTimeout, ConnectionError) as exc:
                if attempt < self.max_retry_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                reason = exc.reason if isinstance(exc, URLError) else str(exc)
                raise GitHubProviderError(f"GitHub request failed: {reason}") from exc

        if not isinstance(payload, dict):
            raise GitHubPayloadError("GitHub search response must be a JSON object")
        return payload

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
        token_label: str | None = None,
    ) -> str:
        request = Request(_build_url(url=url, params=params), headers=headers)
        for attempt in range(1, self.max_retry_attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    self._record_quota_snapshot(
                        status_code=getattr(response, "status", None),
                        headers=response.headers,
                        token_label=token_label,
                        request_url=request.full_url,
                    )
                    payload = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                self._record_quota_snapshot(
                    status_code=exc.code,
                    headers=exc.headers,
                    token_label=token_label,
                    request_url=request.full_url,
                )
                if _is_rate_limited_response(exc):
                    raise GitHubRateLimitError(
                        status_code=exc.code,
                        retry_after_seconds=_parse_retry_after_seconds(exc.headers),
                        token_label=token_label,
                        resource=_parse_rate_limit_resource(exc.headers),
                    ) from exc
                if exc.code == 401:
                    raise GitHubAuthenticationError(
                        f"GitHub request failed with status {exc.code}: {exc.reason}"
                    ) from exc
                if exc.code == 404:
                    raise GitHubReadmeNotFoundError(
                        f"Repository README not found for {url}"
                    ) from exc
                raise GitHubProviderError(
                    f"GitHub request failed with status {exc.code}: {exc.reason}"
                ) from exc
            except (URLError, TimeoutError, SocketTimeout, ConnectionError) as exc:
                if attempt < self.max_retry_attempts:
                    self._sleep_before_retry(attempt)
                    continue
                reason = exc.reason if isinstance(exc, URLError) else str(exc)
                raise GitHubProviderError(f"GitHub request failed: {reason}") from exc

        candidate = payload.strip()
        if not candidate:
            raise GitHubPayloadError("GitHub README response was empty")
        return candidate

    def _record_quota_snapshot(
        self,
        *,
        status_code: int | None,
        headers: object,
        token_label: str | None,
        request_url: str | None,
    ) -> None:
        try:
            write_github_quota_snapshot(
                runtime_dir=self.runtime_dir,
                status_code=status_code,
                headers=headers,
                token_label=token_label,
                token_labels=self.token_labels,
                request_url=request_url,
            )
            if self.quota_observer is not None:
                observation = _build_quota_observation(
                    status_code=status_code,
                    headers=headers,
                    token_label=token_label,
                    request_url=request_url,
                )
                if observation is not None:
                    self.quota_observer(observation)
        except Exception:
            logger.debug("Failed to write GitHub quota snapshot.", exc_info=True)


class GitHubFirehoseProvider:
    SEARCH_REPOSITORIES_URL = "https://api.github.com/search/repositories"
    README_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/readme"
    REPOSITORY_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}"
    CONTRIBUTORS_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/contributors"
    RELEASES_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/releases"
    COMMITS_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/commits"
    PULLS_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/pulls"
    ISSUES_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/issues"
    TREE_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/git/trees/{ref}"
    CONTENTS_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/contents/{path}"
    MAX_SEARCH_PER_PAGE = 100

    def __init__(
        self,
        *,
        transport: GitHubTransport | None = None,
        github_token: str | None,
        github_tokens: tuple[str, ...] | list[str] | None = None,
        runtime_dir: Path | None = None,
        today: date | None = None,
    ) -> None:
        configured_tokens = [
            token.strip()
            for token in [*(github_tokens or ()), github_token]
            if isinstance(token, str) and token.strip()
        ]
        deduped_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in configured_tokens:
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            deduped_tokens.append(token)
        self._token_pool = _shared_token_pool(
            tokens=deduped_tokens or [None],
            runtime_dir=runtime_dir,
        )
        token_labels = self._token_pool.labels()
        self.transport = transport or UrllibGitHubTransport(
            runtime_dir=runtime_dir,
            quota_observer=self._observe_quota_snapshot,
            token_labels=token_labels,
        )
        self.today = today or _utc_today()
        initialize_github_quota_snapshot(
            runtime_dir=runtime_dir,
            token_labels=token_labels,
        )

    def discover(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: date | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        if mode is FirehoseMode.NEW:
            return self._discover_new_repositories(
                anchor_date=anchor_date,
                per_page=per_page,
                page=page,
            )

        payload = self._request_json_object(
            url=self.SEARCH_REPOSITORIES_URL,
            user_agent="agentic-workflow-firehose",
            params=self._build_params(
                mode=mode,
                anchor_date=anchor_date,
                per_page=per_page,
                page=page,
            ),
            resource="search",
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=mode) for item in items]

    def discover_backfill(
        self,
        *,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        payload = self._request_json_object(
            url=self.SEARCH_REPOSITORIES_URL,
            user_agent="agentic-workflow-backfill",
            params=self._build_backfill_params(
                window_start_date=window_start_date,
                created_before_boundary=created_before_boundary,
                created_before_cursor=created_before_cursor,
                per_page=per_page,
                page=page,
            ),
            resource="search",
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=None) for item in items]

    def get_readme(
        self,
        *,
        owner_login: str,
        repository_name: str,
    ) -> RepositoryReadme:
        content = self._request_text(
            url=self.README_URL_TEMPLATE.format(
                owner=owner_login,
                repository=repository_name,
            ),
            user_agent="agentic-workflow-analyst",
            params={},
            resource="core",
            accept="application/vnd.github.raw+json",
        )
        if not content.strip():
            raise GitHubPayloadError("GitHub README response was empty")
        return RepositoryReadme(
            owner_login=owner_login,
            repository_name=repository_name,
            content=content,
            fetched_at=datetime.now(timezone.utc),
            source_url=self.README_URL_TEMPLATE.format(
                owner=owner_login,
                repository=repository_name,
            ),
        )

    def get_repository_metadata(
        self,
        *,
        owner_login: str,
        repository_name: str,
    ) -> RepositoryMetadata:
        source_url = self.REPOSITORY_URL_TEMPLATE.format(
            owner=owner_login,
            repository=repository_name,
        )
        payload = self._request_json_object(
            url=source_url,
            user_agent="agentic-workflow-analyst",
            params={},
            resource="core",
        )
        return RepositoryMetadata(
            owner_login=owner_login,
            repository_name=repository_name,
            full_name=self._optional_string(payload, "full_name") or f"{owner_login}/{repository_name}",
            default_branch=self._optional_string(payload, "default_branch"),
            description=self._optional_string(payload, "description"),
            homepage=self._optional_string(payload, "homepage"),
            primary_language=self._optional_string(payload, "language"),
            license_name=self._extract_license_name(payload),
            topics=self._extract_topics(payload),
            stargazers_count=self._optional_non_negative_int(payload, "stargazers_count"),
            forks_count=self._optional_non_negative_int(payload, "forks_count"),
            open_issues_count=self._optional_non_negative_int(payload, "open_issues_count"),
            subscribers_count=self._optional_non_negative_int(payload, "subscribers_count"),
            created_at=self._optional_datetime(payload, "created_at"),
            pushed_at=self._optional_datetime(payload, "pushed_at"),
            updated_at=self._optional_datetime(payload, "updated_at"),
            source_url=source_url,
            fetched_at=datetime.now(timezone.utc),
        )

    def list_contributors(
        self,
        *,
        owner_login: str,
        repository_name: str,
        limit: int = 5,
    ) -> list[RepositoryContributor]:
        payload = self._request_json_list(
            url=self.CONTRIBUTORS_URL_TEMPLATE.format(owner=owner_login, repository=repository_name),
            user_agent="agentic-workflow-analyst",
            params={"per_page": str(limit)},
        )
        contributors: list[RepositoryContributor] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            login = self._optional_string(item, "login")
            contributions = self._optional_non_negative_int(item, "contributions")
            if login:
                contributors.append(
                    RepositoryContributor(login=login, contributions=contributions)
                )
        return contributors

    def list_releases(
        self,
        *,
        owner_login: str,
        repository_name: str,
        limit: int = 10,
    ) -> list[RepositoryRelease]:
        payload = self._request_json_list(
            url=self.RELEASES_URL_TEMPLATE.format(owner=owner_login, repository=repository_name),
            user_agent="agentic-workflow-analyst",
            params={"per_page": str(limit)},
        )
        releases: list[RepositoryRelease] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            tag_name = self._optional_string(item, "tag_name")
            if not tag_name:
                continue
            releases.append(
                RepositoryRelease(
                    tag_name=tag_name,
                    published_at=self._optional_datetime(item, "published_at"),
                    draft=bool(item.get("draft", False)),
                    prerelease=bool(item.get("prerelease", False)),
                )
            )
        return releases

    def list_recent_commits(
        self,
        *,
        owner_login: str,
        repository_name: str,
        limit: int = 100,
    ) -> list[RepositoryCommit]:
        payload = self._request_json_list(
            url=self.COMMITS_URL_TEMPLATE.format(owner=owner_login, repository=repository_name),
            user_agent="agentic-workflow-analyst",
            params={"per_page": str(limit)},
        )
        commits: list[RepositoryCommit] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            sha = self._optional_string(item, "sha")
            commit = item.get("commit")
            committed_at = None
            if isinstance(commit, dict):
                committer = commit.get("committer")
                if isinstance(committer, dict):
                    committed_at = self._optional_datetime(committer, "date")
            if sha:
                commits.append(RepositoryCommit(sha=sha, committed_at=committed_at))
        return commits

    def list_recent_pull_requests(
        self,
        *,
        owner_login: str,
        repository_name: str,
        limit: int = 50,
    ) -> list[RepositoryPullRequest]:
        payload = self._request_json_list(
            url=self.PULLS_URL_TEMPLATE.format(owner=owner_login, repository=repository_name),
            user_agent="agentic-workflow-analyst",
            params={"state": "all", "per_page": str(limit)},
        )
        pull_requests: list[RepositoryPullRequest] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            number = item.get("number")
            state = self._optional_string(item, "state")
            if not isinstance(number, int) or not state:
                continue
            pull_requests.append(
                RepositoryPullRequest(
                    number=number,
                    merged_at=self._optional_datetime(item, "merged_at"),
                    state=state,
                    created_at=self._optional_datetime(item, "created_at"),
                    closed_at=self._optional_datetime(item, "closed_at"),
                )
            )
        return pull_requests

    def list_recent_issues(
        self,
        *,
        owner_login: str,
        repository_name: str,
        limit: int = 50,
    ) -> list[RepositoryIssue]:
        payload = self._request_json_list(
            url=self.ISSUES_URL_TEMPLATE.format(owner=owner_login, repository=repository_name),
            user_agent="agentic-workflow-analyst",
            params={"state": "all", "per_page": str(limit)},
        )
        issues: list[RepositoryIssue] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("pull_request"), dict):
                continue
            number = item.get("number")
            state = self._optional_string(item, "state")
            if not isinstance(number, int) or not state:
                continue
            issues.append(
                RepositoryIssue(
                    number=number,
                    state=state,
                    created_at=self._optional_datetime(item, "created_at"),
                    updated_at=self._optional_datetime(item, "updated_at"),
                )
            )
        return issues

    def get_repository_tree(
        self,
        *,
        owner_login: str,
        repository_name: str,
        ref: str = "HEAD",
        depth_limit: int = 2,
    ) -> list[RepositoryTreeEntry]:
        payload = self._request_json_object(
            url=self.TREE_URL_TEMPLATE.format(owner=owner_login, repository=repository_name, ref=ref),
            user_agent="agentic-workflow-analyst",
            params={"recursive": "1"},
            resource="core",
        )
        tree = payload.get("tree")
        if not isinstance(tree, list):
            raise GitHubPayloadError("GitHub tree response missing tree list")
        entries: list[RepositoryTreeEntry] = []
        for item in tree:
            if not isinstance(item, dict):
                continue
            path = self._optional_string(item, "path")
            entry_type = self._optional_string(item, "type")
            if not path or not entry_type:
                continue
            if path.count("/") > depth_limit:
                continue
            entries.append(RepositoryTreeEntry(path=path, entry_type=entry_type))
        return entries

    def get_file_contents(
        self,
        *,
        owner_login: str,
        repository_name: str,
        path: str,
    ) -> RepositoryFileSnapshot | None:
        source_url = self.CONTENTS_URL_TEMPLATE.format(
            owner=owner_login,
            repository=repository_name,
            path=path.lstrip("/"),
        )
        try:
            content = self._request_text(
                url=source_url,
                user_agent="agentic-workflow-analyst",
                params={},
                resource="core",
                accept="application/vnd.github.raw+json",
            )
        except GitHubReadmeNotFoundError:
            return None
        return RepositoryFileSnapshot(
            path=path,
            content=content,
            fetched_at=datetime.now(timezone.utc),
            source_url=source_url,
        )

    def _build_headers(
        self,
        *,
        user_agent: str,
        accept: str = "application/vnd.github+json",
        token: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _build_params(
        self,
        *,
        mode: FirehoseMode,
        anchor_date: date | None,
        per_page: int,
        page: int,
    ) -> dict[str, str]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than zero")
        if page <= 0:
            raise ValueError("page must be greater than zero")

        effective_anchor = anchor_date or self._default_anchor_date(mode)
        params = {
            "page": str(page),
            "per_page": str(self._clamp_per_page(per_page, setting_name="FIREHOSE_PER_PAGE")),
        }
        if mode is FirehoseMode.NEW:
            params["q"] = f"created:>={effective_anchor:%Y-%m-%d} archived:false is:public"
            params["sort"] = "created"
            params["order"] = "desc"
            return params

        params["order"] = "desc"
        params["q"] = (
            f"pushed:>={effective_anchor:%Y-%m-%d} "
            "stars:>=50 archived:false is:public"
        )
        params["sort"] = "stars"
        return params

    def _build_backfill_params(
        self,
        *,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None,
        per_page: int,
        page: int,
    ) -> dict[str, str]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than zero")
        if page <= 0:
            raise ValueError("page must be greater than zero")
        if window_start_date >= created_before_boundary:
            raise ValueError("window_start_date must be before created_before_boundary")

        window_end_date = created_before_boundary - timedelta(days=1)
        if created_before_cursor is not None:
            query = (
                f"created:>={window_start_date:%Y-%m-%d} "
                f"created:<={_format_github_timestamp(created_before_cursor)} "
                "archived:false is:public"
            )
        else:
            # GitHub repository search is more reliable with a single created range than
            # separate lower/upper created qualifiers for fresh window scans.
            query = (
                f"created:{window_start_date:%Y-%m-%d}..{window_end_date:%Y-%m-%d} "
                "archived:false is:public"
            )
        return {
            "page": str(page),
            "per_page": str(self._clamp_per_page(per_page, setting_name="BACKFILL_PER_PAGE")),
            "q": query,
            "sort": "created",
            "order": "desc",
        }

    # --- IdeaScout discovery ---

    def discover_idea_scout(
        self,
        *,
        query_prefix: str,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None = None,
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        """Search GitHub for repos matching *query_prefix* within a time window.

        The query_prefix already contains the user's search terms and qualifiers
        like ``archived:false is:public``.  This method appends the ``created:``
        date range from the checkpoint state.
        """
        payload = self._request_json_object(
            url=self.SEARCH_REPOSITORIES_URL,
            user_agent="agentic-workflow-idea-scout",
            params=self._build_idea_scout_params(
                query_prefix=query_prefix,
                window_start_date=window_start_date,
                created_before_boundary=created_before_boundary,
                created_before_cursor=created_before_cursor,
                per_page=per_page,
                page=page,
            ),
            resource="search",
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=None) for item in items]

    def _build_idea_scout_params(
        self,
        *,
        query_prefix: str,
        window_start_date: date,
        created_before_boundary: date,
        created_before_cursor: datetime | None,
        per_page: int,
        page: int,
    ) -> dict[str, str]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than zero")
        if page <= 0:
            raise ValueError("page must be greater than zero")
        if window_start_date >= created_before_boundary:
            raise ValueError("window_start_date must be before created_before_boundary")

        window_end_date = created_before_boundary - timedelta(days=1)
        if created_before_cursor is not None:
            date_qualifier = (
                f"created:>={window_start_date:%Y-%m-%d} "
                f"created:<={_format_github_timestamp(created_before_cursor)}"
            )
        else:
            date_qualifier = (
                f"created:{window_start_date:%Y-%m-%d}..{window_end_date:%Y-%m-%d}"
            )

        # Strip any existing archived/is:public qualifiers from the prefix
        # to avoid duplicates, then append the date range
        query = f"{query_prefix} {date_qualifier}"
        return {
            "page": str(page),
            "per_page": str(self._clamp_per_page(per_page, setting_name="IDEA_SCOUT_PER_PAGE")),
            "q": query,
            "sort": "created",
            "order": "desc",
        }

    def _clamp_per_page(self, per_page: int, *, setting_name: str) -> int:
        if per_page > self.MAX_SEARCH_PER_PAGE:
            logger.warning(
                "%s=%d exceeds GitHub's max page size of %d; clamping request size.",
                setting_name,
                per_page,
                self.MAX_SEARCH_PER_PAGE,
            )
        return min(per_page, self.MAX_SEARCH_PER_PAGE)

    def _discover_new_repositories(
        self,
        *,
        anchor_date: date | None,
        per_page: int,
        page: int,
    ) -> list[DiscoveredRepository]:
        # GitHub returns results sorted by creation date (newest first) via
        # sort=created&order=desc in _build_params, so a single page request
        # guarantees deterministic freshness without client-side sampling or re-sorting.
        payload = self._request_json_object(
            url=self.SEARCH_REPOSITORIES_URL,
            user_agent="agentic-workflow-firehose",
            params=self._build_params(
                mode=FirehoseMode.NEW,
                anchor_date=anchor_date,
                per_page=per_page,
                page=page,
            ),
            resource="search",
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=FirehoseMode.NEW) for item in items]

    def _default_anchor_date(self, mode: FirehoseMode) -> date:
        if mode is FirehoseMode.NEW:
            return self.today - timedelta(days=1)
        return self.today - timedelta(days=7)

    @staticmethod
    def _extract_items(payload: dict[str, object]) -> list[dict[str, object]]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise GitHubPayloadError("GitHub search response missing items list")
        if not all(isinstance(item, dict) for item in items):
            raise GitHubPayloadError("Repository payload item must be an object")
        return items

    def _normalize_repository(
        self,
        item: object,
        *,
        mode: FirehoseMode | None,
    ) -> DiscoveredRepository:
        if not isinstance(item, dict):
            raise GitHubPayloadError("Repository payload item must be an object")

        repository_id = item.get("id")
        if not isinstance(repository_id, int):
            raise GitHubPayloadError("Repository payload missing integer id")

        repository_name = self._require_string(item, "name")
        owner = item.get("owner")
        if not isinstance(owner, dict):
            raise GitHubPayloadError("Repository payload missing required field owner.login")
        owner_login = self._require_string(owner, "login", field_name="owner.login")
        full_name = f"{owner_login}/{repository_name}"

        return DiscoveredRepository(
            github_repository_id=repository_id,
            owner_login=owner_login,
            repository_name=repository_name,
            full_name=full_name,
            created_at=self._require_datetime(item, "created_at"),
            description=self._optional_string(item, "description"),
            stargazers_count=self._optional_non_negative_int(item, "stargazers_count"),
            forks_count=self._optional_non_negative_int(item, "forks_count"),
            pushed_at=self._require_datetime(item, "pushed_at"),
            firehose_discovery_mode=mode,
        )

    @staticmethod
    def _require_string(
        payload: dict[str, object],
        key: str,
        *,
        field_name: str | None = None,
    ) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GitHubPayloadError(
                f"Repository payload missing required field {field_name or key}"
            )
        return value.strip()

    @staticmethod
    def _optional_string(payload: dict[str, object], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise GitHubPayloadError(f"Repository payload field {key} must be a string or null")
        candidate = value.strip()
        return candidate or None

    @staticmethod
    def _require_datetime(payload: dict[str, object], key: str) -> datetime:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GitHubPayloadError(f"Repository payload missing required field {key}")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GitHubPayloadError(
                f"Repository payload field {key} must be an ISO 8601 datetime"
            ) from exc
        if parsed.tzinfo is None:
            raise GitHubPayloadError(
                f"Repository payload field {key} must include a timezone offset"
            )
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _optional_non_negative_int(payload: dict[str, object], key: str) -> int:
        value = payload.get(key)
        if value is None:
            return 0
        if not isinstance(value, int) or value < 0:
            raise GitHubPayloadError(
                f"Repository payload field {key} must be a non-negative integer"
            )
        return value

    def _request_json_list(
        self,
        *,
        url: str,
        user_agent: str,
        params: dict[str, str],
    ) -> list[object]:
        payload = self._request_text(
            url=url,
            user_agent=user_agent,
            params=params,
            resource="core",
        )
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise GitHubPayloadError(f"GitHub response from {url} must be valid JSON") from exc
        if not isinstance(decoded, list):
            raise GitHubPayloadError(f"GitHub response from {url} must be a JSON list")
        return decoded

    def _request_json_object(
        self,
        *,
        url: str,
        user_agent: str,
        params: dict[str, str],
        resource: str,
        accept: str = "application/vnd.github+json",
    ) -> dict[str, object]:
        last_error: GitHubAuthenticationError | None = None
        for _ in range(self._token_pool.token_count()):
            with self._token_pool.lease(resource) as token_selection:
                try:
                    return self.transport.get_json(
                        url=url,
                        headers=self._build_headers(
                            user_agent=user_agent,
                            accept=accept,
                            token=token_selection.token,
                        ),
                        params=params,
                        token_label=token_selection.label,
                    )
                except GitHubAuthenticationError as exc:
                    self._token_pool.mark_unauthorized(
                        token_label=token_selection.label,
                        resource=resource,
                    )
                    last_error = exc
                    logger.warning(
                        "GitHub token %s returned 401 and was quarantined from the pool.",
                        token_selection.label,
                    )
        if last_error is not None:
            raise last_error
        raise GitHubProviderError("GitHub token pool could not satisfy the request")

    def _request_text(
        self,
        *,
        url: str,
        user_agent: str,
        params: dict[str, str],
        resource: str,
        accept: str = "application/vnd.github+json",
    ) -> str:
        last_error: GitHubAuthenticationError | None = None
        for _ in range(self._token_pool.token_count()):
            with self._token_pool.lease(resource) as token_selection:
                try:
                    return self.transport.get_text(
                        url=url,
                        headers=self._build_headers(
                            user_agent=user_agent,
                            accept=accept,
                            token=token_selection.token,
                        ),
                        params=params,
                        token_label=token_selection.label,
                    )
                except GitHubAuthenticationError as exc:
                    self._token_pool.mark_unauthorized(
                        token_label=token_selection.label,
                        resource=resource,
                    )
                    last_error = exc
                    logger.warning(
                        "GitHub token %s returned 401 and was quarantined from the pool.",
                        token_selection.label,
                    )
        if last_error is not None:
            raise last_error
        raise GitHubProviderError("GitHub token pool could not satisfy the request")

    # --- Token health polling ---

    RATE_LIMIT_URL = "https://api.github.com/rate_limit"

    def poll_rate_limits(self) -> None:
        """Fetch live rate-limit data for all configured tokens and update snapshots.

        GitHub's /rate_limit endpoint does NOT consume any API quota — it is
        specifically designed for health checks.  This is safe to call at any
        frequency.
        """
        for label in self._token_pool.labels():
            token = self._token_pool.token_for_label(label)
            try:
                payload = self.transport.get_json(
                    url=self.RATE_LIMIT_URL,
                    headers=self._build_headers(
                        user_agent="agentic-workflow-health-check",
                        accept="application/vnd.github+json",
                        token=token,
                    ),
                    params={},
                    token_label=label,
                )
                now = datetime.now(timezone.utc)
                resources = payload.get("resources", {})
                for resource_name, bucket in resources.items():
                    if not isinstance(bucket, dict):
                        continue
                    reset_ts = bucket.get("reset")
                    reset_at: datetime | None = None
                    if isinstance(reset_ts, (int, float)):
                        reset_at = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
                    remaining = bucket.get("remaining")
                    observation = GitHubQuotaObservation(
                        token_label=label,
                        captured_at=now,
                        status_code=200,
                        request_url=self.RATE_LIMIT_URL,
                        resource=resource_name,
                        limit=bucket.get("limit"),
                        remaining=remaining,
                        used=bucket.get("used"),
                        reset_at=reset_at,
                        retry_after_seconds=None,
                        exhausted=isinstance(remaining, int) and remaining <= 0,
                    )
                    self._token_pool.observe(observation)
            except Exception:
                logger.debug("Rate limit poll failed for token %s", label, exc_info=True)

    def _observe_quota_snapshot(self, observation: GitHubQuotaObservation) -> None:
        self._token_pool.observe(observation)

    @staticmethod
    def _optional_datetime(payload: dict[str, object], key: str) -> datetime | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise GitHubPayloadError(f"Repository payload field {key} must be an ISO 8601 datetime or null")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GitHubPayloadError(
                f"Repository payload field {key} must be an ISO 8601 datetime"
            ) from exc
        if parsed.tzinfo is None:
            raise GitHubPayloadError(
                f"Repository payload field {key} must include a timezone offset"
            )
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _extract_topics(payload: dict[str, object]) -> list[str]:
        value = payload.get("topics")
        if value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise GitHubPayloadError("Repository payload field topics must be list[str] or null")
        return [item.strip() for item in value if item.strip()]

    @staticmethod
    def _extract_license_name(payload: dict[str, object]) -> str | None:
        value = payload.get("license")
        if value is None:
            return None
        if not isinstance(value, dict):
            raise GitHubPayloadError("Repository payload field license must be an object or null")
        return GitHubFirehoseProvider._optional_string(value, "spdx_id") or GitHubFirehoseProvider._optional_string(value, "name")


def _shared_token_pool(
    *,
    tokens: list[str | None],
    runtime_dir: Path | None,
) -> GitHubTokenPool:
    normalized_tokens = tuple(tokens or [None])
    runtime_key = str(runtime_dir.resolve()) if runtime_dir is not None else None
    key = (normalized_tokens, runtime_key, 1.0, 2.0)
    with _TOKEN_POOL_REGISTRY_LOCK:
        pool = _TOKEN_POOL_REGISTRY.get(key)
        if pool is None:
            pool = GitHubTokenPool(
                list(normalized_tokens),
                runtime_dir=runtime_dir,
                core_min_interval_seconds=1.0,
                search_min_interval_seconds=2.0,
            )
            _TOKEN_POOL_REGISTRY[key] = pool
        return pool


def _format_github_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _parse_retry_after_seconds(headers: object) -> int | None:
    if headers is None:
        return None

    raw_value = getattr(headers, "get", lambda _key, _default=None: None)("Retry-After")
    if raw_value is not None:
        try:
            return max(0, int(str(raw_value).strip()))
        except ValueError:
            pass

    reset_value = getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Reset")
    if reset_value is None:
        return None
    try:
        reset_timestamp = int(str(reset_value).strip())
    except ValueError:
        return None

    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    return max(0, reset_timestamp - current_timestamp)


def _parse_rate_limit_resource(headers: object) -> str | None:
    if headers is None:
        return None
    raw_value = getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Resource")
    if not isinstance(raw_value, str):
        return None
    candidate = raw_value.strip()
    return candidate or None


def _build_quota_observation(
    *,
    status_code: int | None,
    headers: object,
    token_label: str | None,
    request_url: str | None,
) -> GitHubQuotaObservation | None:
    if headers is None:
        return None

    limit = _parse_optional_header_int(getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Limit"))
    remaining = _parse_optional_header_int(
        getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Remaining")
    )
    used = _parse_optional_header_int(getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Used"))
    reset_unix = _parse_optional_header_int(
        getattr(headers, "get", lambda _key, _default=None: None)("X-RateLimit-Reset")
    )
    resource = _parse_rate_limit_resource(headers)

    if limit is None and remaining is None and used is None and reset_unix is None and resource is None:
        return None

    captured_at = datetime.now(timezone.utc)
    reset_at = datetime.fromtimestamp(reset_unix, tz=timezone.utc) if reset_unix is not None else None
    retry_after_seconds = _parse_retry_after_seconds(headers)
    exhausted = remaining <= 0 if remaining is not None else None
    return GitHubQuotaObservation(
        token_label=token_label,
        captured_at=captured_at,
        status_code=status_code,
        request_url=request_url,
        resource=resource,
        limit=limit,
        remaining=remaining,
        used=used,
        reset_at=reset_at,
        retry_after_seconds=retry_after_seconds,
        exhausted=exhausted,
    )


def _parse_optional_header_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _observation_remaining(observation: GitHubQuotaObservation | None) -> int:
    if observation is None or observation.remaining is None:
        return -1
    return observation.remaining


def _cooldown_sort_key(cooldown_until: datetime | None) -> float:
    if cooldown_until is None:
        return float("inf")
    return cooldown_until.timestamp()


def _last_used_sort_key(last_used_at: datetime | None) -> float:
    if last_used_at is None:
        return float("-inf")
    return last_used_at.timestamp()


def _is_rate_limited_response(error: HTTPError) -> bool:
    if error.code == 429:
        return True

    headers = error.headers
    if headers is None:
        return False

    get = getattr(headers, "get", lambda _key, _default=None: None)
    return bool(get("Retry-After")) or str(get("X-RateLimit-Remaining", "")).strip() == "0"


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _build_url(*, url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params)}"
