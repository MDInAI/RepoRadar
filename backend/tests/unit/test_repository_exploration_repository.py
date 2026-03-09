from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from sqlmodel import Session, create_engine

from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SQLModel,
)
from app.repositories.repository_exploration_repository import (
    RepositoryCatalogListParams,
    RepositoryExplorationRepository,
)


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'repository-catalog.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_catalog(session: Session) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    repositories = [
        RepositoryIntake(
            github_repository_id=101,
            owner_login="octocat",
            repository_name="growth-engine",
            full_name="octocat/growth-engine",
            repository_description="AI workflow for growth teams",
            stargazers_count=500,
            forks_count=50,
            pushed_at=now,
            discovery_source=RepositoryDiscoverySource.FIREHOSE,
            firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=RepositoryTriageStatus.ACCEPTED,
            analysis_status=RepositoryAnalysisStatus.COMPLETED,
            discovered_at=now,
            queue_created_at=now,
            status_updated_at=now,
            triaged_at=now,
            analysis_started_at=now,
            analysis_completed_at=now,
            analysis_last_attempted_at=now,
        ),
        RepositoryIntake(
            github_repository_id=202,
            owner_login="acme",
            repository_name="backfill-crm",
            full_name="acme/backfill-crm",
            repository_description="CRM toolkit for sales ops",
            stargazers_count=250,
            forks_count=75,
            pushed_at=now.replace(day=8),
            discovery_source=RepositoryDiscoverySource.BACKFILL,
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=RepositoryTriageStatus.REJECTED,
            analysis_status=RepositoryAnalysisStatus.FAILED,
            discovered_at=now.replace(day=8),
            queue_created_at=now.replace(day=8),
            status_updated_at=now.replace(day=8),
            triaged_at=now.replace(day=8),
        ),
        RepositoryIntake(
            github_repository_id=303,
            owner_login="studio",
            repository_name="insight-board",
            full_name="studio/insight-board",
            repository_description="Business research dashboard for operators",
            stargazers_count=800,
            forks_count=25,
            pushed_at=now.replace(day=7),
            discovery_source=RepositoryDiscoverySource.FIREHOSE,
            firehose_discovery_mode=RepositoryFirehoseMode.NEW,
            queue_status=RepositoryQueueStatus.COMPLETED,
            triage_status=RepositoryTriageStatus.ACCEPTED,
            analysis_status=RepositoryAnalysisStatus.PENDING,
            discovered_at=now.replace(day=7),
            queue_created_at=now.replace(day=7),
            status_updated_at=now.replace(day=7),
            triaged_at=now.replace(day=7),
        ),
    ]
    session.add_all(repositories)
    session.add_all(
        [
            RepositoryAnalysisResult(
                github_repository_id=101,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                pros=["Strong funnel"],
                analyzed_at=now,
            ),
            RepositoryAnalysisResult(
                github_repository_id=202,
                monetization_potential=RepositoryMonetizationPotential.LOW,
                pros=["Niche"],
                analyzed_at=now.replace(day=8),
            ),
        ]
    )
    session.add_all(
        [
            RepositoryArtifact(
                github_repository_id=101,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="readmes/101.md",
                content_sha256="a" * 64,
                byte_size=100,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=now,
            ),
            RepositoryArtifact(
                github_repository_id=101,
                artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                runtime_relative_path="analyses/101.json",
                content_sha256="b" * 64,
                byte_size=200,
                content_type="application/json",
                source_kind="repository_analysis",
                generated_at=now,
            ),
            RepositoryArtifact(
                github_repository_id=303,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="readmes/303.md",
                content_sha256="c" * 64,
                byte_size=120,
                content_type="text/markdown",
                source_kind="repository_readme",
                generated_at=now.replace(day=7),
            ),
        ]
    )
    session.commit()


def test_list_repository_catalog_returns_default_sort_and_pagination(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(
            RepositoryCatalogListParams(
                page=1,
                page_size=2,
                search=None,
                discovery_source=None,
                triage_status=None,
                analysis_status=None,
                monetization_potential=None,
                min_stars=None,
                max_stars=None,
                starred_only=False,
                user_tag=None,
                sort_by="stars",
                sort_order="desc",
            )
        )

    assert page.total == 1
    assert page.page == 1
    assert page.page_size == 2
    assert page.total_pages == 1
    assert [item.github_repository_id for item in page.items] == [101]
    assert page.items[0].monetization_potential is RepositoryMonetizationPotential.HIGH
    assert page.items[0].has_readme_artifact is True
    assert page.items[0].has_analysis_artifact is True
    assert page.items[0].is_starred is False
    assert page.items[0].user_tags == []


def test_list_repository_catalog_supports_combined_filters_and_search(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(
            RepositoryCatalogListParams(
                page=1,
                page_size=30,
                search="growth",
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.COMPLETED,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                min_stars=300,
                max_stars=None,
                starred_only=False,
                user_tag=None,
                sort_by="pushed_at",
                sort_order="desc",
            )
        )

    assert page.total == 1
    assert [item.github_repository_id for item in page.items] == [101]
    assert page.items[0].full_name == "octocat/growth-engine"


def _default_params(**overrides: object) -> RepositoryCatalogListParams:
    defaults = dict(
        page=1,
        page_size=30,
        search=None,
        discovery_source=None,
        triage_status=None,
        analysis_status=None,
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


def test_filter_by_discovery_source_alone(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(
            _default_params(discovery_source=RepositoryDiscoverySource.BACKFILL)
        )
    assert page.total == 0
    assert page.items == []


def test_filter_by_triage_status_alone(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(
            _default_params(triage_status=RepositoryTriageStatus.ACCEPTED)
        )
    assert page.total == 2
    ids = {item.github_repository_id for item in page.items}
    assert ids == {101, 303}


def test_filter_by_analysis_status_alone(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(
            _default_params(analysis_status=RepositoryAnalysisStatus.PENDING)
        )
    assert page.total == 1
    assert page.items[0].github_repository_id == 303


def test_filter_by_monetization_potential_alone(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        # HIGH matches repo 101 only (303 has no analysis result)
        page = repo.list_repository_catalog(
            _default_params(monetization_potential=RepositoryMonetizationPotential.HIGH)
        )
    assert page.total == 1
    assert page.items[0].github_repository_id == 101


def test_filter_by_monetization_potential_excludes_null(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        # LOW matches only repo 202; repo 303 has NULL monetization (no analysis result)
        page = repo.list_repository_catalog(
            _default_params(monetization_potential=RepositoryMonetizationPotential.LOW)
        )
    assert page.total == 0
    assert page.items == []


def test_filter_by_min_stars_alone(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(_default_params(min_stars=400))
    assert page.total == 1
    assert page.items[0].github_repository_id == 101


def test_filter_by_star_range(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(_default_params(min_stars=400, max_stars=600))
    assert page.total == 1
    assert page.items[0].github_repository_id == 101


def test_search_escapes_like_special_characters(tmp_path: Path) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        session.add_all(
            [
                RepositoryIntake(
                    github_repository_id=404,
                    owner_login="literal",
                    repository_name="test%repo",
                    full_name="literal/test%repo",
                    repository_description="Percent literal repository",
                    stargazers_count=410,
                    forks_count=41,
                    pushed_at=now,
                    discovery_source=RepositoryDiscoverySource.FIREHOSE,
                    firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                    queue_status=RepositoryQueueStatus.COMPLETED,
                    triage_status=RepositoryTriageStatus.ACCEPTED,
                    analysis_status=RepositoryAnalysisStatus.COMPLETED,
                    discovered_at=now,
                    queue_created_at=now,
                    status_updated_at=now,
                    triaged_at=now,
                    analysis_started_at=now,
                    analysis_completed_at=now,
                    analysis_last_attempted_at=now,
                ),
                RepositoryIntake(
                    github_repository_id=405,
                    owner_login="literal",
                    repository_name="user_repo",
                    full_name="literal/user_repo",
                    repository_description="Underscore literal repository",
                    stargazers_count=420,
                    forks_count=42,
                    pushed_at=now,
                    discovery_source=RepositoryDiscoverySource.BACKFILL,
                    queue_status=RepositoryQueueStatus.COMPLETED,
                    triage_status=RepositoryTriageStatus.ACCEPTED,
                    analysis_status=RepositoryAnalysisStatus.COMPLETED,
                    discovered_at=now,
                    queue_created_at=now,
                    status_updated_at=now,
                    triaged_at=now,
                    analysis_started_at=now,
                    analysis_completed_at=now,
                    analysis_last_attempted_at=now,
                ),
                RepositoryIntake(
                    github_repository_id=406,
                    owner_login="literal",
                    repository_name=r"slash\repo",
                    full_name=r"literal/slash\repo",
                    repository_description=r"Stored at folder\repo",
                    stargazers_count=430,
                    forks_count=43,
                    pushed_at=now,
                    discovery_source=RepositoryDiscoverySource.FIREHOSE,
                    firehose_discovery_mode=RepositoryFirehoseMode.NEW,
                    queue_status=RepositoryQueueStatus.COMPLETED,
                    triage_status=RepositoryTriageStatus.ACCEPTED,
                    analysis_status=RepositoryAnalysisStatus.COMPLETED,
                    discovered_at=now,
                    queue_created_at=now,
                    status_updated_at=now,
                    triaged_at=now,
                    analysis_started_at=now,
                    analysis_completed_at=now,
                    analysis_last_attempted_at=now,
                ),
            ]
        )
        session.commit()
        repo = RepositoryExplorationRepository(session)

        percent_page = repo.list_repository_catalog(_default_params(search="test%repo"))
        underscore_page = repo.list_repository_catalog(_default_params(search="user_repo"))
        backslash_page = repo.list_repository_catalog(_default_params(search=r"folder\repo"))

    assert [item.github_repository_id for item in percent_page.items] == [404]
    assert [item.github_repository_id for item in underscore_page.items] == [405]
    assert [item.github_repository_id for item in backslash_page.items] == [406]


def test_sort_by_forks_asc(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(_default_params(sort_by="forks", sort_order="asc"))
    assert [item.github_repository_id for item in page.items] == [101]


def test_sort_by_ingested_at_desc(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        page = repo.list_repository_catalog(
            _default_params(sort_by="ingested_at", sort_order="desc")
        )
    assert [item.github_repository_id for item in page.items] == [101]


def test_invalid_sort_by_raises_value_error(tmp_path: Path) -> None:
    import pytest

    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repo = RepositoryExplorationRepository(session)
        with pytest.raises(ValueError, match="Unsupported sort_by"):
            repo.list_repository_catalog(_default_params(sort_by="nonexistent"))


def test_list_repository_catalog_supports_sorting_and_empty_page(tmp_path: Path) -> None:
    with _make_session(tmp_path) as session:
        _seed_catalog(session)
        repository = RepositoryExplorationRepository(session)

        page = repository.list_repository_catalog(
            RepositoryCatalogListParams(
                page=3,
                page_size=2,
                search=None,
                discovery_source=None,
                triage_status=None,
                analysis_status=None,
                monetization_potential=None,
                min_stars=200,
                max_stars=None,
                starred_only=False,
                user_tag=None,
                sort_by="forks",
                sort_order="asc",
            )
        )

    assert page.total == 1
    assert page.total_pages == 1
    assert page.items == []


def test_list_repository_catalog_meets_sub_second_query_target_at_10k_repos(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

    with _make_session(tmp_path) as session:
        session.add_all(
            [
                RepositoryIntake(
                    github_repository_id=10_000 + index,
                    owner_login=f"owner{index}",
                    repository_name=f"repo{index}",
                    full_name=f"owner{index}/repo{index}",
                    repository_description=f"Repository {index}",
                    stargazers_count=20_000 - index,
                    forks_count=index % 250,
                    pushed_at=now,
                    discovery_source=RepositoryDiscoverySource.FIREHOSE,
                    firehose_discovery_mode=RepositoryFirehoseMode.TRENDING,
                    queue_status=RepositoryQueueStatus.COMPLETED,
                    triage_status=RepositoryTriageStatus.ACCEPTED,
                    analysis_status=RepositoryAnalysisStatus.COMPLETED,
                    discovered_at=now,
                    queue_created_at=now,
                    status_updated_at=now,
                    triaged_at=now,
                    analysis_started_at=now,
                    analysis_completed_at=now,
                    analysis_last_attempted_at=now,
                )
                for index in range(10_000)
            ]
        )
        session.add_all(
            [
                RepositoryAnalysisResult(
                    github_repository_id=10_000 + index,
                    monetization_potential=RepositoryMonetizationPotential.HIGH,
                    pros=["Scalable funnel"],
                    analyzed_at=now,
                )
                for index in range(10_000)
            ]
        )
        session.commit()

        repository = RepositoryExplorationRepository(session)
        start = perf_counter()
        page = repository.list_repository_catalog(_default_params(page_size=30))
        elapsed_seconds = perf_counter() - start

    assert page.total == 10_000
    assert len(page.items) == 30
    assert elapsed_seconds < 1.0
