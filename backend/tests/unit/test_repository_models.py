from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlmodel import Session, create_engine

from app.models import (
    BackfillProgress,
    FirehoseProgress,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryUserCuration,
    RepositoryUserTag,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
    SQLModel,
)
from app.models.repository import UTCDateTimeType


def test_repository_intake_defaults_cover_queue_baseline() -> None:
    record = RepositoryIntake(
        github_repository_id=123456,
        owner_login="octocat",
        repository_name="hello-world",
        full_name="octocat/hello-world",
    )

    assert record.source_provider == "github"
    assert record.discovery_source is RepositoryDiscoverySource.UNKNOWN
    assert record.firehose_discovery_mode is None
    assert record.queue_status is RepositoryQueueStatus.PENDING
    assert record.triage_status is RepositoryTriageStatus.PENDING
    assert record.discovered_at is not None
    assert record.queue_created_at is not None
    assert record.status_updated_at is not None
    assert record.processing_started_at is None
    assert record.processing_completed_at is None
    assert record.last_failed_at is None
    assert record.repository_description is None
    assert record.stargazers_count == 0
    assert record.forks_count == 0
    assert record.pushed_at is None
    assert record.triaged_at is None
    assert record.analysis_status is RepositoryAnalysisStatus.PENDING
    assert record.analysis_started_at is None
    assert record.analysis_completed_at is None
    assert record.analysis_last_attempted_at is None
    assert record.analysis_last_failed_at is None
    assert record.analysis_failure_code is None
    assert record.analysis_failure_message is None
    # Default intake timestamps must be UTC-aware (from _utcnow default_factory)
    assert record.discovered_at.tzinfo == timezone.utc
    assert record.queue_created_at.tzinfo == timezone.utc
    assert record.status_updated_at.tzinfo == timezone.utc


def test_utc_datetime_type_rejects_naive_datetimes() -> None:
    type_instance = UTCDateTimeType()
    with pytest.raises(ValueError, match="timezone-aware"):
        type_instance.process_bind_param(datetime(2026, 3, 7, 12, 0, 0), dialect=None)


def test_utc_datetime_type_accepts_and_normalizes_aware_datetimes() -> None:
    type_instance = UTCDateTimeType()
    aware = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    result = type_instance.process_bind_param(aware, dialect=None)
    # Result should be naive (tzinfo stripped for SQLite storage) and UTC-equivalent
    assert result is not None
    assert result.tzinfo is None
    assert result == aware.replace(tzinfo=None)


def test_repository_intake_metadata_uses_canonical_identity_and_query_indexes() -> None:
    table = RepositoryIntake.__table__

    assert list(table.primary_key.columns.keys()) == ["github_repository_id"]
    assert table.c.queue_status.type.enums == [status.value for status in RepositoryQueueStatus]
    assert table.c.triage_status.type.enums == [status.value for status in RepositoryTriageStatus]
    assert table.c.analysis_status.type.enums == [
        status.value for status in RepositoryAnalysisStatus
    ]
    assert table.c.analysis_failure_code.type.enums == [
        status.value for status in RepositoryAnalysisFailureCode
    ]
    assert table.c.discovery_source.type.enums == [
        source.value for source in RepositoryDiscoverySource
    ]
    assert table.c.firehose_discovery_mode.type.enums == [
        source.value for source in RepositoryFirehoseMode
    ]
    assert {index.name for index in table.indexes} == {
        "ix_repository_intake_discovery_source",
        "ix_repository_intake_full_name",
        "ix_repository_intake_analysis_status",
        "ix_repository_intake_pushed_at",
        "ix_repository_intake_queue_status",
        "ix_repository_intake_triage_status",
    }


def test_backfill_progress_defaults_support_durable_resume_state() -> None:
    record = BackfillProgress(
        window_start_date=date(2026, 2, 1),
        created_before_boundary=date(2026, 3, 1),
    )

    assert record.source_provider == "github"
    assert record.created_before_cursor is None
    assert record.next_page == 1
    assert record.pages_processed_in_run == 0
    assert record.exhausted is False
    assert record.last_checkpointed_at is None
    assert record.updated_at.tzinfo == timezone.utc

    table = BackfillProgress.__table__
    assert list(table.primary_key.columns.keys()) == ["source_provider"]


def test_repository_triage_explanation_defaults_capture_snapshot_shape() -> None:
    explained_at = datetime(2026, 3, 8, 12, 30, tzinfo=timezone.utc)
    record = RepositoryTriageExplanation(
        github_repository_id=123,
        explanation_kind=RepositoryTriageExplanationKind.INCLUDE_RULE,
        explanation_summary="Accepted because include rules matched: saas.",
        explained_at=explained_at,
    )

    assert record.github_repository_id == 123
    assert record.explanation_kind is RepositoryTriageExplanationKind.INCLUDE_RULE
    assert record.explanation_summary == "Accepted because include rules matched: saas."
    assert record.matched_include_rules == []
    assert record.matched_exclude_rules == []
    assert record.explained_at == explained_at

    table = RepositoryTriageExplanation.__table__
    assert list(table.primary_key.columns.keys()) == ["github_repository_id"]
    assert table.c.explanation_kind.type.enums == [
        kind.value for kind in RepositoryTriageExplanationKind
    ]
    assert not table.c.explanation_summary.nullable
    assert not table.c.matched_include_rules.nullable
    assert not table.c.matched_exclude_rules.nullable
    assert not table.c.explained_at.nullable


def test_repository_user_curation_defaults_capture_starred_state() -> None:
    record = RepositoryUserCuration(github_repository_id=123)

    assert record.github_repository_id == 123
    assert record.is_starred is False
    assert record.starred_at is None
    assert record.updated_at.tzinfo == timezone.utc

    table = RepositoryUserCuration.__table__
    assert list(table.primary_key.columns.keys()) == ["github_repository_id"]
    assert {index.name for index in table.indexes} == {"ix_repository_user_curation_is_starred"}


def test_repository_user_tag_defaults_capture_operator_labels() -> None:
    created_at = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    record = RepositoryUserTag(
        github_repository_id=123,
        tag_label="workflow",
        created_at=created_at,
    )

    assert record.github_repository_id == 123
    assert record.tag_label == "workflow"
    assert record.created_at == created_at

    table = RepositoryUserTag.__table__
    assert table.c.tag_label.type.length == 100
    assert {index.name for index in table.indexes} == {"ix_repository_user_tag_github_repository_id"}
    assert any(
        constraint.name == "uq_repository_user_tag_github_repository_id_tag_label"
        for constraint in table.constraints
    )


def test_repository_triage_explanation_tracks_in_place_rule_list_mutations() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        intake = RepositoryIntake(
            github_repository_id=456,
            owner_login="octocat",
            repository_name="saas-platform",
            full_name="octocat/saas-platform",
        )
        explanation = RepositoryTriageExplanation(
            github_repository_id=456,
            explanation_kind=RepositoryTriageExplanationKind.INCLUDE_RULE,
            explanation_summary="Accepted because include rules matched: saas.",
            matched_include_rules=["saas"],
            explained_at=datetime(2026, 3, 8, 12, 30, tzinfo=timezone.utc),
        )
        session.add(intake)
        session.add(explanation)
        session.commit()

        persisted = session.get(RepositoryTriageExplanation, 456)
        assert persisted is not None
        persisted.matched_include_rules.append("developer tools")
        session.add(persisted)
        session.commit()
        session.expire_all()

        reloaded = session.get(RepositoryTriageExplanation, 456)

    assert reloaded is not None
    assert reloaded.matched_include_rules == ["saas", "developer tools"]


def test_repository_analysis_result_defaults_capture_structured_snapshot() -> None:
    analyzed_at = datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc)
    record = RepositoryAnalysisResult(
        github_repository_id=789,
        monetization_potential=RepositoryMonetizationPotential.HIGH,
        pros=["Clear API story"],
        cons=["Pricing unclear"],
        missing_feature_signals=["Missing billing detail"],
        source_metadata={"readme_artifact_path": "data/readmes/789.md"},
        analyzed_at=analyzed_at,
    )

    assert record.github_repository_id == 789
    assert record.source_provider == "github"
    assert record.source_kind == "repository_readme"
    assert record.source_metadata == {"readme_artifact_path": "data/readmes/789.md"}
    assert record.monetization_potential is RepositoryMonetizationPotential.HIGH
    assert record.category_confidence_score is None
    assert record.agent_tags == []
    assert record.suggested_new_categories == []
    assert record.suggested_new_tags == []
    assert record.pros == ["Clear API story"]
    assert record.cons == ["Pricing unclear"]
    assert record.missing_feature_signals == ["Missing billing detail"]
    assert record.problem_statement is None
    assert record.target_customer is None
    assert record.product_type is None
    assert record.business_model_guess is None
    assert record.technical_stack is None
    assert record.target_audience is None
    assert record.open_problems is None
    assert record.competitors is None
    assert record.confidence_score is None
    assert record.recommended_action is None
    assert record.analyzed_at == analyzed_at

    table = RepositoryAnalysisResult.__table__
    assert list(table.primary_key.columns.keys()) == ["github_repository_id"]
    assert table.c.monetization_potential.type.enums == [
        value.value for value in RepositoryMonetizationPotential
    ]
    assert not table.c.source_metadata.nullable
    assert not table.c.agent_tags.nullable
    assert not table.c.suggested_new_categories.nullable
    assert not table.c.suggested_new_tags.nullable
    assert not table.c.pros.nullable
    assert not table.c.cons.nullable
    assert not table.c.missing_feature_signals.nullable


def test_repository_artifact_defaults_capture_durable_payload_reference() -> None:
    generated_at = datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc)
    record = RepositoryArtifact(
        github_repository_id=789,
        artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
        runtime_relative_path="data/readmes/789.md",
        content_sha256="a" * 64,
        byte_size=128,
        content_type="text/markdown; charset=utf-8",
        source_kind="repository_readme",
        source_url="https://api.github.com/repos/octocat/repo/readme",
        provenance_metadata={"normalization_version": "story-3.4-v1"},
        generated_at=generated_at,
    )

    assert record.github_repository_id == 789
    assert record.artifact_kind is RepositoryArtifactKind.README_SNAPSHOT
    assert record.runtime_relative_path == "data/readmes/789.md"
    assert record.content_sha256 == "a" * 64
    assert record.byte_size == 128
    assert record.content_type == "text/markdown; charset=utf-8"
    assert record.source_kind == "repository_readme"
    assert record.source_url == "https://api.github.com/repos/octocat/repo/readme"
    assert record.provenance_metadata == {"normalization_version": "story-3.4-v1"}
    assert record.generated_at == generated_at

    table = RepositoryArtifact.__table__
    assert list(table.primary_key.columns.keys()) == ["github_repository_id", "artifact_kind"]
    assert table.c.artifact_kind.type.enums == [value.value for value in RepositoryArtifactKind]
    assert not table.c.runtime_relative_path.nullable
    assert not table.c.content_sha256.nullable
    assert not table.c.byte_size.nullable


def test_firehose_progress_defaults_support_resume_state() -> None:
    record = FirehoseProgress()

    assert record.source_provider == "github"
    assert record.active_mode is None
    assert record.next_page == 1
    assert record.pages_processed_in_run == 0
    assert record.new_anchor_date is None
    assert record.trending_anchor_date is None
    assert record.run_started_at is None
    assert record.resume_required is False
    assert record.last_checkpointed_at is None
    assert record.updated_at.tzinfo == timezone.utc

    table = FirehoseProgress.__table__
    assert list(table.primary_key.columns.keys()) == ["source_provider"]
