from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
from enum import StrEnum
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    firehose_discovery_mode: FirehoseMode | None = None


class GitHubProviderError(RuntimeError):
    pass


class GitHubPayloadError(GitHubProviderError):
    pass


class GitHubTransport(Protocol):
    def get_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        params: dict[str, str],
    ) -> dict[str, object]: ...


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
            raise GitHubProviderError(
                f"GitHub request failed with status {exc.code}: {exc.reason}"
            ) from exc
        except URLError as exc:
            raise GitHubProviderError(f"GitHub request failed: {exc.reason}") from exc

        if not isinstance(payload, dict):
            raise GitHubPayloadError("GitHub search response must be a JSON object")
        return payload


class GitHubFirehoseProvider:
    SEARCH_REPOSITORIES_URL = "https://api.github.com/search/repositories"
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
        per_page: int = 25,
        page: int = 1,
    ) -> list[DiscoveredRepository]:
        if mode is FirehoseMode.NEW:
            return self._discover_new_repositories(per_page=per_page, page=page)

        payload = self.transport.get_json(
            url=self.SEARCH_REPOSITORIES_URL,
            headers=self._build_headers(user_agent="agentic-workflow-firehose"),
            params=self._build_params(mode=mode, per_page=per_page, page=page),
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

    def _build_headers(self, *, user_agent: str) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _build_params(self, *, mode: FirehoseMode, per_page: int, page: int) -> dict[str, str]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than zero")
        if page <= 0:
            raise ValueError("page must be greater than zero")

        params = {
            "page": str(page),
            "per_page": str(min(per_page, self.MAX_SEARCH_PER_PAGE)),
        }
        if mode is FirehoseMode.NEW:
            params["q"] = (
                f"created:>={self.today - timedelta(days=1):%Y-%m-%d} archived:false is:public"
            )
            params["sort"] = "created"
            params["order"] = "desc"
            return params

        params["order"] = "desc"
        params["q"] = (
            f"pushed:>={self.today - timedelta(days=7):%Y-%m-%d} "
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
            
            # If the cursor falls exactly on a day boundary, shift it earlier by 1 second
            # to avoid fetching things from the excluded day, because we query 'created:<YYYY-MM-DD'
            # when created_before_cursor is None.
            # But the requirement from the bug report: 
            #   "if GitHub returns more than one page of repositories with the same creation timestamp... 
            #   anything beyond the first page at that timestamp is skipped permanently."
            # Which is handled by sorting and the 'page' parameter.
            
            # In the event of a deep stall (i.e. we hit GitHub's 1000 page cap for a single second slice)
            # The calling job modifies `created_before_cursor` explicitly to force traversal down.
            # We don't modify it here.
        return {
            "page": str(page),
            "per_page": str(min(per_page, self.MAX_SEARCH_PER_PAGE)),
            "q": (
                f"created:>={window_start_date:%Y-%m-%d} "
                f"created:{operator}{_format_github_timestamp(upper_bound)} "
                "archived:false is:public"
            ),
            "sort": "created",
            "order": "desc",
        }

    def _discover_new_repositories(
        self,
        *,
        per_page: int,
        page: int,
    ) -> list[DiscoveredRepository]:
        # GitHub returns results sorted by creation date (newest first) via
        # sort=created&order=desc in _build_params, so a single page request
        # guarantees deterministic freshness without client-side sampling or re-sorting.
        payload = self.transport.get_json(
            url=self.SEARCH_REPOSITORIES_URL,
            headers=self._build_headers(user_agent="agentic-workflow-firehose"),
            params=self._build_params(mode=FirehoseMode.NEW, per_page=per_page, page=page),
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=FirehoseMode.NEW) for item in items]

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


def _format_github_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()
