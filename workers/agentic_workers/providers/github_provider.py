from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
    firehose_discovery_mode: FirehoseMode


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
        self.today = today or date.today()

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
            headers=self._build_headers(),
            params=self._build_params(mode=mode, per_page=per_page, page=page),
        )
        items = self._extract_items(payload)
        return [self._normalize_repository(item, mode=mode) for item in items]

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "agentic-workflow-firehose",
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
            headers=self._build_headers(),
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
        mode: FirehoseMode,
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
