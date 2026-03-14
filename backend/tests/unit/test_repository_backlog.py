from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
)
from app.repositories.repository_exploration_repository import (
    RepositoryCatalogListParams,
    RepositoryExplorationRepository,
)
from app.schemas.repository_exploration import (
    RepositoryCatalogQueryParams,
    RepositoryCatalogSortBy,
    RepositoryCatalogSortOrder,
)
from app.services.repository_exploration_service import RepositoryExplorationService


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'repository-backlog.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_backlog(session: Session) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            RepositoryIntake(
                github_repository_id=101,
                source_provider="github",
                owner_login="alpha",
                repository_name="queued-repo",
                full_name="alpha/queued-repo",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                stargazers_count=5,
                forks_count=1,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            ),
            RepositoryIntake(
                github_repository_id=202,
                source_provider="github",
                owner_login="beta",
                repository_name="processing-repo",
                full_name="beta/processing-repo",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.IN_PROGRESS,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.IN_PROGRESS,
                stargazers_count=10,
                forks_count=2,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                processing_started_at=now.replace(hour=11, minute=45),
                analysis_started_at=now,
                triaged_at=now,
            ),
            RepositoryIntake(
                github_repository_id=303,
                source_provider="github",
                owner_login="gamma",
                repository_name="completed-repo",
                full_name="gamma/completed-repo",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                stargazers_count=15,
                forks_count=3,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                processing_started_at=now.replace(hour=11, minute=40),
                processing_completed_at=now.replace(hour=11, minute=50),
                analysis_started_at=now,
                analysis_completed_at=now,
                triaged_at=now,
            ),
            RepositoryIntake(
                github_repository_id=404,
                source_provider="github",
                owner_login="delta",
                repository_name="queue-failed-repo",
                full_name="delta/queue-failed-repo",
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.FAILED,
                triage_status=RepositoryTriageStatus.REJECTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
                stargazers_count=20,
                forks_count=4,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                last_failed_at=now,
            ),
            RepositoryIntake(
                github_repository_id=505,
                source_provider="github",
                owner_login="epsilon",
                repository_name="analysis-failed-repo",
                full_name="epsilon/analysis-failed-repo",
                repository_description="Failed during analysis",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.FAILED,
                stargazers_count=25,
                forks_count=5,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
                processing_started_at=now.replace(hour=11, minute=35),
                processing_completed_at=now.replace(hour=11, minute=55),
                last_failed_at=now.replace(hour=11, minute=58),
                triaged_at=now,
                analysis_started_at=now,
                analysis_completed_at=now,
                analysis_last_failed_at=now,
                analysis_failure_code=RepositoryAnalysisFailureCode.RATE_LIMITED,
                analysis_failure_message="Upstream provider throttled the request repeatedly.",
            ),
        ]
    )
    session.commit()


def _default_params(**overrides: object) -> RepositoryCatalogListParams:
    defaults = dict(
        page=1,
        page_size=30,
        search=None,
        discovery_source=None,
        queue_status=None,
        triage_status=None,
        analysis_status=None,
        has_failures=False,
        monetization_potential=None,
        min_stars=None,
        max_stars=None,
        starred_only=False,
        user_tag=None,
        sort_by="stars",
        sort_order="desc",
    )
    defaults.update(overrides)
    return RepositoryCatalogListParams(**defaults)  # type: ignore[arg-type]


def test_repository_backlog_summary_returns_counts_for_each_status_dimension(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        service = RepositoryExplorationService(RepositoryExplorationRepository(session))

        summary = service.get_repository_backlog_summary()

    assert summary.queue.model_dump() == {
        "pending": 1,
        "in_progress": 1,
        "completed": 2,
        "failed": 1,
    }
    assert summary.triage.model_dump() == {
        "pending": 1,
        "accepted": 3,
        "rejected": 1,
    }
    assert summary.analysis.model_dump() == {
        "pending": 2,
        "in_progress": 1,
        "completed": 1,
        "failed": 1,
    }


def test_repository_backlog_summary_returns_zeroed_counts_for_empty_database(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        service = RepositoryExplorationService(RepositoryExplorationRepository(session))

        summary = service.get_repository_backlog_summary()

    assert summary.queue.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }
    assert summary.triage.model_dump() == {"pending": 0, "accepted": 0, "rejected": 0}
    assert summary.analysis.model_dump() == {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
    }


def test_repository_catalog_supports_queue_status_filter_for_backlog_views(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(
            _default_params(queue_status=RepositoryQueueStatus.PENDING)
        )

    assert page.total == 1
    assert [item.github_repository_id for item in page.items] == [101]
    assert page.items[0].intake_status is RepositoryQueueStatus.PENDING


def test_repository_catalog_supports_has_failures_filter_for_queue_or_analysis_failures(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(_default_params(has_failures=True))

    assert page.total == 2
    assert [item.github_repository_id for item in page.items] == [505, 404]


def test_repository_catalog_maps_failure_context_fields_for_failed_repositories(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        service = RepositoryExplorationService(RepositoryExplorationRepository(session))

        page = service.list_repository_catalog(
            RepositoryCatalogQueryParams(
                analysis_status=RepositoryAnalysisStatus.FAILED,
                sort_by=RepositoryCatalogSortBy.STARS,
                sort_order=RepositoryCatalogSortOrder.DESC,
            )
        )

    assert page.total == 1
    item = page.items[0]
    assert item.github_repository_id == 505
    assert item.intake_status.value == "completed"
    assert item.queue_created_at == now
    assert item.processing_started_at == now
    assert item.processing_completed_at == now
    assert item.intake_failed_at == now.replace(hour=11, minute=58)
    assert item.analysis_failed_at == now
    assert item.failure is not None
    assert item.failure.stage == "analysis"
    assert item.failure.error_code == "rate_limited"
    assert item.failure.error_message == "Upstream provider throttled the request repeatedly."


def test_repository_catalog_uses_analysis_timestamps_with_queue_failure_fallback(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(_default_params(has_failures=True))

    assert [item.github_repository_id for item in page.items] == [505, 404]

    analysis_failed = page.items[0]
    assert analysis_failed.processing_started_at == now
    assert analysis_failed.processing_completed_at == now
    assert analysis_failed.intake_failed_at == now.replace(hour=11, minute=58)
    assert analysis_failed.analysis_failed_at == now

    queue_failed = page.items[1]
    assert queue_failed.processing_started_at is None
    assert queue_failed.processing_completed_at is None
    assert queue_failed.intake_failed_at == now
    assert queue_failed.analysis_failed_at is None
    assert queue_failed.failure is not None
    assert queue_failed.failure.stage == "intake"


def test_repository_backlog_summary_executes_in_a_single_query(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_backlog(session)
        repository = RepositoryExplorationRepository(session)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture_statement(
            _conn: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture_statement)
        try:
            repository.get_repository_backlog_summary()
        finally:
            event.remove(engine, "before_cursor_execute", _capture_statement)

    assert len(statements) == 1
