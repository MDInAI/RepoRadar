from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from enum import StrEnum
import json
import logging
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


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


class GitHubProviderError(RuntimeError):
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
    ) -> None:
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
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
    ) -> dict[str, object]: ...

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> str: ...


class UrllibGitHubTransport:
    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> dict[str, object]:
        request = Request(f"{url}?{urlencode(params)}", headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if _is_rate_limited_response(exc):
                raise GitHubRateLimitError(
                    status_code=exc.code,
                    retry_after_seconds=_parse_retry_after_seconds(exc.headers),
                ) from exc
            raise GitHubProviderError(
                f"GitHub request failed with status {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise GitHubProviderError(f"GitHub request failed: {exc.reason}") from exc

        if not isinstance(payload, dict):
            raise GitHubPayloadError("GitHub search response must be a JSON object")
        return payload

    def get_text(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> str:
        request = Request(_build_url(url=url, params=params), headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            if _is_rate_limited_response(exc):
                raise GitHubRateLimitError(
                    status_code=exc.code,
                    retry_after_seconds=_parse_retry_after_seconds(exc.headers),
                ) from exc
            if exc.code == 404:
                raise GitHubReadmeNotFoundError(
                    f"Repository README not found for {url}"
                ) from exc
            raise GitHubProviderError(
                f"GitHub request failed with status {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise GitHubProviderError(f"GitHub request failed: {exc.reason}") from exc

        candidate = payload.strip()
        if not candidate:
            raise GitHubPayloadError("GitHub README response was empty")
        return candidate


class GitHubFirehoseProvider:
    SEARCH_REPOSITORIES_URL = "https://api.github.com/search/repositories"
    README_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repository}/readme"
    MAX_SEARCH_PER_PAGE = 100

    def __init__(
        self,
        *,
        transport: GitHubTransport | None = None,
        github_token: str | None,
        today: date | None = None,
    ) -> None:
        self.transport = transport or UrllibGitHubTransport()
        self.github_token = github_token
        self.today = today or _utc_today()

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

        payload = self.transport.get_json(
            url=self.SEARCH_REPOSITORIES_URL,
            headers=self._build_headers(user_agent="agentic-workflow-firehose"),
            params=self._build_params(
                mode=mode,
                anchor_date=anchor_date,
                per_page=per_page,
                page=page,
            ),
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
        payload = self.transport.get_json(
            url=self.SEARCH_REPOSITORIES_URL,
            headers=self._build_headers(user_agent="agentic-workflow-backfill"),
            params=self._build_backfill_params(
                window_start_date=window_start_date,
                created_before_boundary=created_before_boundary,
                created_before_cursor=created_before_cursor,
                per_page=per_page,
                page=page,
            ),
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=None) for item in items]

    def get_readme(
        self,
        *,
        owner_login: str,
        repository_name: str,
    ) -> RepositoryReadme:
        content = self.transport.get_text(
            url=self.README_URL_TEMPLATE.format(
                owner=owner_login,
                repository=repository_name,
            ),
            headers=self._build_headers(
                user_agent="agentic-workflow-analyst",
                accept="application/vnd.github.raw+json",
            ),
            params={},
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

    def _build_headers(
        self,
        *,
        user_agent: str,
        accept: str = "application/vnd.github+json",
    ) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
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

        operator = "<"
        upper_bound = datetime.combine(
            created_before_boundary,
            time.min,
            tzinfo=timezone.utc,
        )
        if created_before_cursor is not None:
            operator = "<="
            upper_bound = created_before_cursor
        return {
            "page": str(page),
            "per_page": str(self._clamp_per_page(per_page, setting_name="BACKFILL_PER_PAGE")),
            "q": (
                f"created:>={window_start_date:%Y-%m-%d} "
                f"created:{operator}{_format_github_timestamp(upper_bound)} "
                "archived:false is:public"
            ),
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
        payload = self.transport.get_json(
            url=self.SEARCH_REPOSITORIES_URL,
            headers=self._build_headers(user_agent="agentic-workflow-firehose"),
            params=self._build_params(
                mode=FirehoseMode.NEW,
                anchor_date=anchor_date,
                per_page=per_page,
                page=page,
            ),
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


def _format_github_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _parse_retry_after_seconds(headers: object) -> int | None:
    if headers is None:
        return None

    raw_value = getattr(headers, "get", lambda _key, _default=None: None)("Retry-After")
    if raw_value is None:
        return None
    try:
        return max(0, int(str(raw_value).strip()))
    except ValueError:
        return None


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
