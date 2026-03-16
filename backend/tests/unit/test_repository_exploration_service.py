from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import pytest
from sqlmodel import Session, create_engine

from app.core.errors import AppError
from app.models import (
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryArtifactPayload,
    RepositoryCategory,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
    SQLModel,
)
from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.services.repository_exploration_service import RepositoryExplorationService
from app.schemas.repository_exploration import RepositoryCatalogQueryParams


def _make_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'repository-exploration.db'}")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _make_service(session: Session, *, runtime_dir: Path | None = None) -> RepositoryExplorationService:
    return RepositoryExplorationService(
        RepositoryExplorationRepository(session),
        RepositoryArtifactPayloadRepository(session, runtime_dir=runtime_dir),
    )


def test_repository_exploration_service_returns_joined_metadata_summary_and_artifacts(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 11, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=707,
                owner_login="octocat",
                repository_name="analyze-me",
                full_name="octocat/analyze-me",
                repository_description="Automation platform for SaaS teams",
                stargazers_count=321,
                forks_count=45,
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
            )
        )
        session.add(
            RepositoryAnalysisResult(
                github_repository_id=707,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                category_confidence_score=88,
                agent_tags=["workflow", "automation"],
                suggested_new_categories=["sales_ops"],
                suggested_new_tags=["self-serve"],
                pros=["Clear workflow"],
                cons=["Pricing unclear"],
                missing_feature_signals=["Missing billing"],
                problem_statement="Teams need workflow automation without bespoke tooling.",
                target_customer="SaaS operators",
                product_type="workflow platform",
                business_model_guess="usage-based SaaS",
                technical_stack="Next.js, Postgres, background workers",
                target_audience="Operations teams",
                open_problems="Still missing packaging and billing evidence.",
                competitors="Zapier, Make",
                confidence_score=84,
                recommended_action="Create family + Combiner brief",
                source_metadata={
                    "readme_artifact_path": "data/readmes/707.md",
                    "analysis_artifact_path": "data/analyses/707.json",
                    "analysis_provider": "StaticAnalysisProvider",
                    "analysis_model_name": "claude-3-5-haiku-20241022",
                    "analysis_mode": "fast",
                    "analysis_outcome": "completed",
                    "analysis_schema_version": "story-3.4-v2",
                    "analysis_evidence_version": "fast-evidence-v1",
                    "evidence_summary": "Deterministic evidence summary.",
                    "analysis_signals": {"has_readme": True, "stars": 321},
                    "score_breakdown": {
                        "technical_maturity_score": 74,
                        "commercial_readiness_score": 63,
                        "hosted_gap_score": 71,
                        "market_timing_score": 58,
                        "trust_risk_score": 22,
                    },
                    "analysis_summary_short": "Short deterministic analyst summary.",
                    "analysis_summary_long": "Long deterministic analyst summary.",
                    "supporting_signals": ["Repository already has 321 GitHub stars."],
                    "red_flags": ["Commercial packaging and pricing evidence is still weak."],
                    "contradictions": ["Hosted claims exceed deployment evidence."],
                    "missing_information": ["Pricing details are missing."],
                    "normalization_version": "story-3.4-v1",
                    "raw_character_count": 3120,
                    "normalized_character_count": 1280,
                    "removed_line_count": 14,
                },
                analyzed_at=now,
            )
        )
        session.add(
            RepositoryTriageExplanation(
                github_repository_id=707,
                explanation_kind=RepositoryTriageExplanationKind.INCLUDE_RULE,
                explanation_summary="Accepted because workflow automation matched the include set.",
                matched_include_rules=["workflow", "automation"],
                matched_exclude_rules=[],
                explained_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/707.md",
                content_sha256="a" * 64,
                byte_size=128,
                content_type="text/markdown; charset=utf-8",
                source_kind="repository_readme",
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
                provenance_metadata={"normalization_version": "story-3.4-v1"},
                generated_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                runtime_relative_path="data/analyses/707.json",
                content_sha256="b" * 64,
                byte_size=256,
                content_type="application/json",
                source_kind="repository_analysis",
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
                provenance_metadata={"analysis_provider": "StaticAnalysisProvider"},
                generated_at=now,
            )
        )
        session.add(
            RepositoryArtifactPayload(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                content_text="# Analyze Me\n\nWorkflow automation for SaaS operators.",
                updated_at=now,
            )
        )
        session.add(
            RepositoryArtifactPayload(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                content_text=json.dumps(
                    {
                        "schema_version": "story-3.4-v1",
                        "github_repository_id": 707,
                        "full_name": "octocat/analyze-me",
                        "analysis_provider": "StaticAnalysisProvider",
                        "analysis": {
                            "monetization_potential": "high",
                            "pros": ["Clear workflow"],
                            "cons": ["Pricing unclear"],
                            "missing_feature_signals": ["Missing billing"],
                        },
                    }
                ),
                updated_at=now,
            )
        )
        session.commit()
        service = _make_service(session)
        response = service.get_repository_exploration(707)

    assert response.github_repository_id == 707
    assert response.full_name == "octocat/analyze-me"
    assert response.owner_login == "octocat"
    assert response.repository_name == "analyze-me"
    assert response.stargazers_count == 321
    assert response.forks_count == 45
    assert response.pushed_at == now
    assert response.intake_status.value == "completed"
    assert response.triage.triage_status.value == "accepted"
    assert response.triage.explanation is not None
    assert response.triage.explanation.kind.value == "include_rule"
    assert response.triage.explanation.matched_include_rules == ["workflow", "automation"]
    assert response.analysis_summary is not None
    assert response.analysis_summary.monetization_potential is RepositoryMonetizationPotential.HIGH
    assert response.analysis_summary.category_confidence_score == 88
    assert response.analysis_summary.agent_tags == ["workflow", "automation"]
    assert response.analysis_summary.suggested_new_categories == ["sales_ops"]
    assert response.analysis_summary.suggested_new_tags == ["self-serve"]
    assert response.analysis_summary.target_customer == "SaaS operators"
    assert response.analysis_summary.confidence_score == 84
    assert response.analysis_summary.recommended_action == "Create family + Combiner brief"
    assert response.analysis_summary.analysis_mode == "fast"
    assert response.analysis_summary.analysis_outcome == "completed"
    assert response.analysis_summary.analysis_schema_version == "story-3.4-v2"
    assert response.analysis_summary.analysis_evidence_version == "fast-evidence-v1"
    assert response.analysis_summary.evidence_summary == "Deterministic evidence summary."
    assert response.analysis_summary.analysis_signals["stars"] == 321
    assert response.analysis_summary.score_breakdown["hosted_gap_score"] == 71
    assert response.analysis_summary.analysis_summary_short == "Short deterministic analyst summary."
    assert response.analysis_summary.analysis_summary_long == "Long deterministic analyst summary."
    assert response.analysis_summary.supporting_signals == [
        "Repository already has 321 GitHub stars."
    ]
    assert response.analysis_summary.red_flags == [
        "Commercial packaging and pricing evidence is still weak."
    ]
    assert response.analysis_summary.contradictions == [
        "Hosted claims exceed deployment evidence."
    ]
    assert response.analysis_summary.missing_information == [
        "Pricing details are missing."
    ]
    assert response.readme_snapshot is not None
    assert response.readme_snapshot.content == "# Analyze Me\n\nWorkflow automation for SaaS operators."
    assert response.readme_snapshot.normalization_version == "story-3.4-v1"
    assert response.analysis_artifact is not None
    assert response.analysis_artifact.provider_name == "StaticAnalysisProvider"
    assert response.analysis_artifact.model_name == "claude-3-5-haiku-20241022"
    assert response.analysis_artifact.payload["analysis"]["pros"] == ["Clear workflow"]
    assert response.processing.intake_created_at == now
    assert response.processing.intake_started_at is None
    assert response.processing.intake_completed_at is None
    assert response.processing.failure is None
    assert response.firehose_discovery_mode is RepositoryFirehoseMode.NEW
    assert response.agent_tags == ["new", "workflow", "automation"]
    assert response.has_readme_artifact is True
    assert response.has_analysis_artifact is True
    assert response.is_starred is False
    assert response.user_tags == []
    assert [artifact.runtime_relative_path for artifact in response.artifacts] == [
        "data/analyses/707.json",
        "data/readmes/707.md",
    ]


def test_repository_exploration_service_raises_not_found_for_missing_repository(
    tmp_path: Path,
) -> None:
    with _make_session(tmp_path) as session:
        service = _make_service(session)
        with pytest.raises(AppError, match="was not found"):
            service.get_repository_exploration(999)


def test_repository_exploration_service_lists_catalog_page(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 11, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=707,
                owner_login="octocat",
                repository_name="analyze-me",
                full_name="octocat/analyze-me",
                repository_description="Automation platform for SaaS teams",
                stargazers_count=321,
                forks_count=45,
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
            )
        )
        session.add(
            RepositoryAnalysisResult(
                github_repository_id=707,
                monetization_potential=RepositoryMonetizationPotential.HIGH,
                category=RepositoryCategory.WORKFLOW,
                category_confidence_score=86,
                confidence_score=79,
                agent_tags=["workflow"],
                suggested_new_tags=["approval"],
                pros=["Clear workflow"],
                cons=["Pricing unclear"],
                missing_feature_signals=["Missing billing"],
                source_metadata={
                    "readme_artifact_path": "data/readmes/707.md",
                    "analysis_outcome": "completed_low_confidence",
                },
                analyzed_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=707,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/707.md",
                content_sha256="a" * 64,
                byte_size=128,
                content_type="text/markdown; charset=utf-8",
                source_kind="repository_readme",
                source_url="https://api.github.com/repos/octocat/analyze-me/readme",
                provenance_metadata={"normalization_version": "story-3.4-v1"},
                generated_at=now,
            )
        )
        session.commit()

        service = _make_service(session)
        response = service.list_repository_catalog(RepositoryCatalogQueryParams())

    assert response.total == 1
    assert response.page == 1
    assert response.page_size == 30
    assert response.total_pages == 1
    assert response.items[0].firehose_discovery_mode is RepositoryFirehoseMode.NEW
    assert len(response.items) == 1
    assert response.items[0].github_repository_id == 707
    assert response.items[0].intake_status is RepositoryQueueStatus.COMPLETED
    assert response.items[0].monetization_potential is RepositoryMonetizationPotential.HIGH
    assert response.items[0].category is RepositoryCategory.WORKFLOW
    assert response.items[0].category_confidence_score == 86
    assert response.items[0].confidence_score == 79
    assert response.items[0].analysis_outcome == "completed_low_confidence"
    assert response.items[0].agent_tags == ["new", "workflow"]
    assert response.items[0].suggested_new_tags == ["approval"]
    assert response.items[0].has_readme_artifact is True
    assert response.items[0].has_analysis_artifact is False
    assert response.items[0].is_starred is False
    assert response.items[0].user_tags == []


def test_repository_exploration_service_preserves_failed_analysis_status_with_artifacts(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 3, 9, 15, 0, tzinfo=timezone.utc)
    with _make_session(tmp_path) as session:
        session.add(
            RepositoryIntake(
                github_repository_id=808,
                owner_login="octocat",
                repository_name="broken-analyzer",
                full_name="octocat/broken-analyzer",
                repository_description="Analysis job failed after README capture",
                stargazers_count=128,
                forks_count=12,
                pushed_at=now,
                discovery_source=RepositoryDiscoverySource.BACKFILL,
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.FAILED,
                discovered_at=now,
                queue_created_at=now,
                processing_started_at=now,
                processing_completed_at=now,
                status_updated_at=now,
                triaged_at=now,
                analysis_started_at=now,
                analysis_last_attempted_at=now,
                analysis_last_failed_at=now,
                analysis_failure_message="Gateway rate limit while analyzing repository.",
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=808,
                artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
                runtime_relative_path="data/readmes/808.md",
                content_sha256="c" * 64,
                byte_size=128,
                content_type="text/markdown; charset=utf-8",
                source_kind="repository_readme",
                generated_at=now,
            )
        )
        session.add(
            RepositoryArtifact(
                github_repository_id=808,
                artifact_kind=RepositoryArtifactKind.ANALYSIS_RESULT,
                runtime_relative_path="data/analyses/808.json",
                content_sha256="d" * 64,
                byte_size=256,
                content_type="application/json",
                source_kind="repository_analysis",
                generated_at=now,
            )
        )
        session.commit()

        runtime_dir = tmp_path / "runtime"
        (runtime_dir / "data" / "readmes").mkdir(parents=True)
        (runtime_dir / "data" / "analyses").mkdir(parents=True)
        (runtime_dir / "data" / "readmes" / "808.md").write_text(
            "# Broken Analyzer\n\nREADME captured before failure.",
            encoding="utf-8",
        )
        (runtime_dir / "data" / "analyses" / "808.json").write_text(
            json.dumps({"status": "partial"}),
            encoding="utf-8",
        )

        service = _make_service(session, runtime_dir=runtime_dir)
        response = service.get_repository_exploration(808)

    assert response.intake_status.value == "completed"
    assert response.analysis_status.value == "failed"
    assert response.has_analysis_artifact is True
    assert response.processing.analysis_failed_at == now
    assert response.processing.failure is not None
    assert response.processing.failure.stage == "analysis"
    assert response.processing.failure.upstream_source == "backfill"
    assert response.processing.failure.error_message == (
        "Gateway rate limit while analyzing repository."
    )
