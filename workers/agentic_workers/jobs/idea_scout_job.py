"""IdeaScout job — idea-driven historical repository discovery.

Mirrors the Backfill job architecture but driven by user-provided ideas.
Each IdeaSearch has one or more search queries, each with its own independent
time-window checkpoint.  The job processes one page per active query per run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import json
import logging
from pathlib import Path
from typing import Callable

from sqlmodel import Session, select

from agentic_workers.core.events import emit_event, emit_failure_event
from agentic_workers.core.failure_detector import (
    classify_github_error,
    classify_github_runtime_error,
    determine_severity,
)
from agentic_workers.core.pause_manager import is_agent_paused
from agentic_workers.core.pause_policy import evaluate_pause_policy
from agentic_workers.providers.github_provider import (
    DiscoveredRepository,
    GitHubFirehoseProvider,
    GitHubProviderError,
    GitHubRateLimitError,
)
from agentic_workers.storage.backend_models import (
    IdeaSearch,
    IdeaSearchDirection,
    IdeaSearchStatus,
)
from agentic_workers.storage.idea_search_intake import persist_idea_scout_batch
from agentic_workers.storage.idea_search_progress import (
    IdeaSearchCheckpointState,
    advance_idea_search_progress,
    initialize_forward_watch_progress,
    initialize_idea_search_progress,
    load_idea_search_progress,
    save_idea_search_progress,
)
from agentic_workers.storage.repository_intake import IntakePersistenceResult


logger = logging.getLogger(__name__)


class IdeaScoutRunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    SKIPPED = "skipped"
    SKIPPED_PAUSED = "skipped_paused"
    NO_WORK = "no_work"


@dataclass(frozen=True, slots=True)
class IdeaScoutPageOutcome:
    idea_search_id: int
    query_index: int
    window_start_date: date
    created_before_boundary: date
    page: int
    fetched_count: int
    inserted_count: int
    skipped_count: int
    exhausted_after: bool
    error: str | None = None
    rate_limit_backoff_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class IdeaScoutRunResult:
    status: IdeaScoutRunStatus
    outcomes: list[IdeaScoutPageOutcome]
    searches_processed: int
    artifact_path: Path | None = None


def run_idea_scout_cycle(
    *,
    session: Session,
    provider: GitHubFirehoseProvider,
    runtime_dir: Path | None,
    pacing_seconds: int,
    per_page: int,
    pages_per_search: int,
    window_days: int,
    min_created_date: date,
    sleep_fn: Callable[[int], None],
    should_stop: Callable[[], bool] | None = None,
    today: date | None = None,
    agent_run_id: int | None = None,
) -> IdeaScoutRunResult:
    """Run one cycle of IdeaScout work across all active searches.

    Processes up to ``pages_per_search`` pages for each active IdeaSearch,
    iterating through queries that haven't been exhausted yet.
    """
    # Check global agent pause
    if is_agent_paused(session, "idea_scout"):
        logger.debug("IdeaScout is paused, skipping cycle")
        return IdeaScoutRunResult(
            status=IdeaScoutRunStatus.SKIPPED_PAUSED,
            outcomes=[],
            searches_processed=0,
        )

    active_today = today or _utc_today()

    # Find all active IdeaSearches
    stmt = select(IdeaSearch).where(IdeaSearch.status == IdeaSearchStatus.ACTIVE.value)
    searches = list(session.exec(stmt).all())

    if not searches:
        return IdeaScoutRunResult(
            status=IdeaScoutRunStatus.NO_WORK,
            outcomes=[],
            searches_processed=0,
        )

    all_outcomes: list[IdeaScoutPageOutcome] = []
    searches_processed = 0

    for search in searches:
        if should_stop is not None and should_stop():
            break
        if is_agent_paused(session, "idea_scout"):
            break

        search_outcomes = _process_single_search(
            session=session,
            provider=provider,
            search=search,
            pacing_seconds=pacing_seconds,
            per_page=per_page,
            pages_per_search=pages_per_search,
            window_days=window_days,
            min_created_date=min_created_date,
            sleep_fn=sleep_fn,
            should_stop=should_stop,
            today=active_today,
            agent_run_id=agent_run_id,
        )
        all_outcomes.extend(search_outcomes)
        searches_processed += 1

    status = _determine_status(all_outcomes)

    # Write artifact
    artifact_path: Path | None = None
    if runtime_dir is not None:
        artifact_path = _write_run_artifact(
            runtime_dir=runtime_dir,
            outcomes=all_outcomes,
            status=status,
            searches_processed=searches_processed,
        )

    return IdeaScoutRunResult(
        status=status,
        outcomes=all_outcomes,
        searches_processed=searches_processed,
        artifact_path=artifact_path,
    )


def _process_single_search(
    *,
    session: Session,
    provider: GitHubFirehoseProvider,
    search: IdeaSearch,
    pacing_seconds: int,
    per_page: int,
    pages_per_search: int,
    window_days: int,
    min_created_date: date,
    sleep_fn: Callable[[int], None],
    should_stop: Callable[[], bool] | None,
    today: date,
    agent_run_id: int | None,
) -> list[IdeaScoutPageOutcome]:
    """Process one IdeaSearch: iterate through its queries, fetch pages."""
    outcomes: list[IdeaScoutPageOutcome] = []
    queries = search.search_queries or []

    if not queries:
        logger.warning("IdeaSearch %d has no search queries, skipping", search.id)
        return outcomes

    is_forward = search.direction == IdeaSearchDirection.FORWARD.value
    pages_used = 0

    for qi, query_text in enumerate(queries):
        if pages_used >= pages_per_search:
            break
        if should_stop is not None and should_stop():
            break

        # Load or initialize checkpoint for this query
        checkpoint = load_idea_search_progress(
            session, idea_search_id=search.id, query_index=qi,
        )
        if checkpoint is None:
            if is_forward:
                checkpoint = initialize_forward_watch_progress(
                    idea_search_id=search.id,
                    query_index=qi,
                    today=today,
                )
            else:
                checkpoint = initialize_idea_search_progress(
                    idea_search_id=search.id,
                    query_index=qi,
                    today=today,
                    window_days=window_days,
                    min_created_date=min_created_date,
                )
            save_idea_search_progress(session, checkpoint, commit=False)
            session.commit()

        if checkpoint.exhausted and not is_forward:
            continue

        # For forward watches, reset window to recent date range each cycle
        if is_forward:
            checkpoint = IdeaSearchCheckpointState(
                idea_search_id=checkpoint.idea_search_id,
                query_index=checkpoint.query_index,
                window_start_date=today - timedelta(days=1),
                created_before_boundary=today + timedelta(days=1),
                created_before_cursor=None,
                next_page=1,
                exhausted=False,
                last_checkpointed_at=checkpoint.last_checkpointed_at,
                resume_required=False,
                pages_processed_in_run=0,
            )

        # Process pages for this query
        remaining = pages_per_search - pages_used
        for page_idx in range(remaining):
            if checkpoint.exhausted:
                break
            if should_stop is not None and should_stop():
                break
            if is_agent_paused(session, "idea_scout"):
                break

            if page_idx > 0 or pages_used > 0:
                sleep_fn(pacing_seconds)
                if should_stop is not None and should_stop():
                    break

            requested_page = checkpoint.next_page
            repositories: list[DiscoveredRepository] = []

            try:
                repositories = provider.discover_idea_scout(
                    query_prefix=query_text,
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    created_before_cursor=checkpoint.created_before_cursor,
                    per_page=per_page,
                    page=requested_page,
                )

                persisted = persist_idea_scout_batch(
                    session,
                    repositories,
                    idea_search_id=search.id,
                    commit=False,
                )

                oldest_created_at = min(
                    (r.created_at for r in repositories),
                    default=None,
                )

                next_checkpoint = advance_idea_search_progress(
                    checkpoint,
                    repositories_fetched=len(repositories),
                    oldest_created_at=oldest_created_at,
                    batch_has_mixed_timestamps=(
                        oldest_created_at is not None
                        and any(r.created_at > oldest_created_at for r in repositories)
                    ),
                    per_page=per_page,
                    window_days=window_days,
                    min_created_date=min_created_date,
                    checkpointed_at=datetime.now(timezone.utc),
                    pages_processed_in_run=checkpoint.pages_processed_in_run + 1,
                )

                save_idea_search_progress(session, next_checkpoint, commit=False)
                session.commit()

                outcomes.append(IdeaScoutPageOutcome(
                    idea_search_id=search.id,
                    query_index=qi,
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    page=requested_page,
                    fetched_count=len(repositories),
                    inserted_count=persisted.inserted_count,
                    skipped_count=persisted.skipped_count,
                    exhausted_after=next_checkpoint.exhausted,
                ))

                if agent_run_id is not None and next_checkpoint.exhausted:
                    try:
                        emit_event(
                            session,
                            event_type="idea_scout_query_exhausted",
                            agent_name="idea_scout",
                            severity="info",
                            message=f"IdeaScout search {search.id} query {qi} exhausted.",
                            context_json=json.dumps({
                                "idea_search_id": search.id,
                                "query_index": qi,
                            }, sort_keys=True),
                            agent_run_id=agent_run_id,
                        )
                    except Exception:
                        logger.warning("Failed to emit exhaustion event", exc_info=True)

                checkpoint = next_checkpoint
                pages_used += 1

            except GitHubRateLimitError as exc:
                session.rollback()
                backoff_seconds = max(pacing_seconds * 2, exc.retry_after_seconds or 0)
                outcomes.append(IdeaScoutPageOutcome(
                    idea_search_id=search.id,
                    query_index=qi,
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    page=requested_page,
                    fetched_count=0,
                    inserted_count=0,
                    skipped_count=0,
                    exhausted_after=False,
                    error=str(exc),
                    rate_limit_backoff_seconds=backoff_seconds,
                ))
                try:
                    classification = classify_github_error(exc)
                    failure_sev = determine_severity(classification, 1)
                    emit_failure_event(
                        session,
                        event_type="rate_limit_hit",
                        agent_name="idea_scout",
                        message=f"IdeaScout hit rate limit on search {search.id}.",
                        classification=classification,
                        failure_severity=failure_sev,
                        http_status_code=exc.status_code,
                        retry_after_seconds=exc.retry_after_seconds,
                        upstream_provider="github",
                        context_json=json.dumps({
                            "idea_search_id": search.id,
                            "query_index": qi,
                            "backoff_seconds": backoff_seconds,
                        }, sort_keys=True),
                        agent_run_id=agent_run_id,
                        commit=True,
                    )
                except Exception:
                    logger.warning("Failed to emit rate_limit_hit event", exc_info=True)
                # Stop processing this search on rate limit
                break

            except GitHubProviderError as exc:
                session.rollback()
                outcomes.append(IdeaScoutPageOutcome(
                    idea_search_id=search.id,
                    query_index=qi,
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    page=requested_page,
                    fetched_count=0,
                    inserted_count=0,
                    skipped_count=0,
                    exhausted_after=False,
                    error=str(exc),
                ))
                try:
                    classification = classify_github_error(exc)
                    failure_sev = determine_severity(classification, 1)
                    emit_failure_event(
                        session,
                        event_type="repository_discovery_failed",
                        agent_name="idea_scout",
                        message=f"IdeaScout provider error on search {search.id}.",
                        classification=classification,
                        failure_severity=failure_sev,
                        http_status_code=getattr(exc, "status_code", None),
                        upstream_provider="github",
                        context_json=json.dumps({
                            "idea_search_id": search.id,
                            "query_index": qi,
                            "error": str(exc),
                        }, sort_keys=True),
                        agent_run_id=agent_run_id,
                        commit=True,
                    )
                except Exception:
                    logger.warning("Failed to emit discovery_failed event", exc_info=True)
                break

            except Exception as exc:
                session.rollback()
                outcomes.append(IdeaScoutPageOutcome(
                    idea_search_id=search.id,
                    query_index=qi,
                    window_start_date=checkpoint.window_start_date,
                    created_before_boundary=checkpoint.created_before_boundary,
                    page=requested_page,
                    fetched_count=0,
                    inserted_count=0,
                    skipped_count=0,
                    exhausted_after=False,
                    error=str(exc),
                ))
                logger.exception(
                    "Unexpected error in IdeaScout search %d query %d",
                    search.id, qi,
                )
                break

    # Check if all queries for this search are exhausted (backward only)
    if not is_forward:
        _check_search_completion(session, search)

    return outcomes


def _check_search_completion(session: Session, search: IdeaSearch) -> None:
    """Mark a backward IdeaSearch as completed if all queries are exhausted."""
    queries = search.search_queries or []
    if not queries:
        return

    all_exhausted = True
    for qi in range(len(queries)):
        cp = load_idea_search_progress(
            session, idea_search_id=search.id, query_index=qi,
        )
        if cp is None or not cp.exhausted:
            all_exhausted = False
            break

    if all_exhausted:
        search.status = IdeaSearchStatus.COMPLETED.value
        search.updated_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("IdeaSearch %d completed — all queries exhausted.", search.id)


def _determine_status(outcomes: list[IdeaScoutPageOutcome]) -> IdeaScoutRunStatus:
    if not outcomes:
        return IdeaScoutRunStatus.NO_WORK
    has_errors = any(o.error is not None for o in outcomes)
    has_successes = any(o.error is None for o in outcomes)
    if has_errors and has_successes:
        return IdeaScoutRunStatus.PARTIAL_FAILURE
    if has_errors:
        return IdeaScoutRunStatus.FAILED
    return IdeaScoutRunStatus.SUCCESS


def _write_run_artifact(
    *,
    runtime_dir: Path,
    outcomes: list[IdeaScoutPageOutcome],
    status: IdeaScoutRunStatus,
    searches_processed: int,
) -> Path | None:
    """Write a JSON artifact summarizing the run."""
    try:
        artifact_dir = runtime_dir / "idea-scout" / "ingestion-runs"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifact_path = artifact_dir / f"{timestamp}.json"

        payload = {
            "status": status.value,
            "searches_processed": searches_processed,
            "outcomes": [
                {
                    "idea_search_id": o.idea_search_id,
                    "query_index": o.query_index,
                    "window_start_date": o.window_start_date.isoformat(),
                    "created_before_boundary": o.created_before_boundary.isoformat(),
                    "page": o.page,
                    "fetched_count": o.fetched_count,
                    "inserted_count": o.inserted_count,
                    "skipped_count": o.skipped_count,
                    "exhausted_after": o.exhausted_after,
                    "error": o.error,
                }
                for o in outcomes
            ],
        }
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return artifact_path
    except Exception:
        logger.warning("Failed to write IdeaScout run artifact", exc_info=True)
        return None


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()
