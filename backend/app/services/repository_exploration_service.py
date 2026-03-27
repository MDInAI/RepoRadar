from __future__ import annotations

import json

from app.core.errors import AppError
from app.models import RepositoryArtifactKind
from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from app.repositories.repository_exploration_repository import (
    RepositoryCatalogListParams,
    RepositoryExplorationRepository,
)
from app.schemas.repository_exploration import (
    RepositoryAnalysisArtifactResponse,
    RepositoryAnalysisSummaryResponse,
    RepositoryArtifactRefResponse,
    RepositoryBacklogSummaryResponse,
    RepositoryCatalogItemResponse,
    RepositoryCatalogPageResponse,
    RepositoryCatalogQueryParams,
    RepositoryFailureContextResponse,
    RepositoryProcessingContextResponse,
    RepositoryProcessingAnalysisSummaryResponse,
    RepositoryProcessingQueueSummaryResponse,
    RepositoryProcessingTriageSummaryResponse,
    RepositoryExplorationResponse,
    RepositoryReadmeSnapshotResponse,
    RepositoryTriageContextResponse,
    RepositoryTriageExplanationResponse,
)


class RepositoryExplorationService:
    def __init__(
        self,
        repository: RepositoryExplorationRepository,
        artifact_payload_repository: RepositoryArtifactPayloadRepository,
    ) -> None:
        self.repository = repository
        self.artifact_payload_repository = artifact_payload_repository

    def get_repository_exploration(
        self,
        github_repository_id: int,
    ) -> RepositoryExplorationResponse:
        record = self.repository.get_repository_exploration(github_repository_id)
        if record is None:
            raise AppError(
                message=f"Repository {github_repository_id} was not found.",
                code="repository_not_found",
                status_code=404,
                details={"github_repository_id": github_repository_id},
            )

        artifact_responses = [
            RepositoryArtifactRefResponse(
                artifact_kind=artifact.artifact_kind,
                runtime_relative_path=artifact.runtime_relative_path,
                content_sha256=artifact.content_sha256,
                byte_size=artifact.byte_size,
                content_type=artifact.content_type,
                source_kind=artifact.source_kind,
                source_url=artifact.source_url,
                provenance_metadata=artifact.provenance_metadata,
                generated_at=artifact.generated_at,
            )
            for artifact in record.artifacts
        ]
        artifacts_by_kind = {
            artifact.artifact_kind: response
            for artifact, response in zip(record.artifacts, artifact_responses, strict=False)
        }
        artifact_kinds = {artifact.artifact_kind for artifact in record.artifacts}

        analysis_summary = None
        if record.analysis_summary is not None:
            analysis_metadata = record.analysis_summary.source_metadata
            analysis_summary = RepositoryAnalysisSummaryResponse(
                monetization_potential=record.analysis_summary.monetization_potential,
                category=record.analysis_summary.category,
                category_confidence_score=record.analysis_summary.category_confidence_score,
                analysis_mode=self._get_str_metadata(analysis_metadata, "analysis_mode"),
                analysis_outcome=self._get_str_metadata(analysis_metadata, "analysis_outcome"),
                analysis_schema_version=self._get_str_metadata(
                    analysis_metadata,
                    "analysis_schema_version",
                ),
                analysis_evidence_version=self._get_str_metadata(
                    analysis_metadata,
                    "analysis_evidence_version",
                ),
                insufficient_evidence_reason=self._get_str_metadata(
                    analysis_metadata,
                    "insufficient_evidence_reason",
                ),
                evidence_summary=self._get_str_metadata(analysis_metadata, "evidence_summary"),
                analysis_signals=self._get_dict_metadata(analysis_metadata, "analysis_signals"),
                score_breakdown=self._get_int_dict_metadata(analysis_metadata, "score_breakdown"),
                analysis_summary_short=self._get_str_metadata(
                    analysis_metadata,
                    "analysis_summary_short",
                ),
                analysis_summary_long=self._get_str_metadata(
                    analysis_metadata,
                    "analysis_summary_long",
                ),
                supporting_signals=self._get_str_list_metadata(
                    analysis_metadata,
                    "supporting_signals",
                ),
                red_flags=self._get_str_list_metadata(analysis_metadata, "red_flags"),
                contradictions=self._get_str_list_metadata(analysis_metadata, "contradictions"),
                missing_information=self._get_str_list_metadata(
                    analysis_metadata,
                    "missing_information",
                ),
                agent_tags=record.analysis_summary.agent_tags,
                suggested_new_categories=record.analysis_summary.suggested_new_categories,
                suggested_new_tags=record.analysis_summary.suggested_new_tags,
                pros=record.analysis_summary.pros,
                cons=record.analysis_summary.cons,
                missing_feature_signals=record.analysis_summary.missing_feature_signals,
                problem_statement=record.analysis_summary.problem_statement,
                target_customer=record.analysis_summary.target_customer,
                product_type=record.analysis_summary.product_type,
                business_model_guess=record.analysis_summary.business_model_guess,
                technical_stack=record.analysis_summary.technical_stack,
                target_audience=record.analysis_summary.target_audience,
                open_problems=record.analysis_summary.open_problems,
                competitors=record.analysis_summary.competitors,
                confidence_score=record.analysis_summary.confidence_score,
                recommended_action=record.analysis_summary.recommended_action,
                source_metadata=record.analysis_summary.source_metadata,
                analyzed_at=record.analysis_summary.analyzed_at,
            )

        explanation = None
        if record.triage.explanation is not None:
            explanation = RepositoryTriageExplanationResponse(
                kind=record.triage.explanation.kind,
                summary=record.triage.explanation.summary,
                matched_include_rules=record.triage.explanation.matched_include_rules,
                matched_exclude_rules=record.triage.explanation.matched_exclude_rules,
                explained_at=record.triage.explanation.explained_at,
            )

        readme_artifact = artifacts_by_kind.get(RepositoryArtifactKind.README_SNAPSHOT)
        analysis_artifact = artifacts_by_kind.get(RepositoryArtifactKind.ANALYSIS_RESULT)
        readme_source_metadata = record.analysis_summary.source_metadata if record.analysis_summary else {}

        readme_snapshot = RepositoryReadmeSnapshotResponse(
            artifact=readme_artifact,
            content=(
                self.artifact_payload_repository.get_text_artifact(
                    record.github_repository_id,
                    RepositoryArtifactKind.README_SNAPSHOT,
                )
                if readme_artifact is not None
                else None
            ),
            normalization_version=self._get_str_metadata(
                readme_artifact.provenance_metadata if readme_artifact is not None else {},
                "normalization_version",
            )
            or self._get_str_metadata(readme_source_metadata, "normalization_version"),
            raw_character_count=self._coalesce_int_metadata(
                readme_artifact.provenance_metadata if readme_artifact is not None else {},
                readme_source_metadata,
                "raw_character_count",
            ),
            normalized_character_count=self._coalesce_int_metadata(
                readme_artifact.provenance_metadata if readme_artifact is not None else {},
                readme_source_metadata,
                "normalized_character_count",
            ),
            removed_line_count=self._coalesce_int_metadata(
                readme_artifact.provenance_metadata if readme_artifact is not None else {},
                readme_source_metadata,
                "removed_line_count",
            ),
        )

        analysis_artifact_response = RepositoryAnalysisArtifactResponse(
            artifact=analysis_artifact,
            provider_name=self._get_str_metadata(readme_source_metadata, "analysis_provider")
            or self._get_str_metadata(
                analysis_artifact.provenance_metadata if analysis_artifact is not None else {},
                "analysis_provider",
            ),
            model_name=self._get_str_metadata(readme_source_metadata, "analysis_model_name")
            or self._get_str_metadata(
                analysis_artifact.provenance_metadata if analysis_artifact is not None else {},
                "analysis_model_name",
            ),
            source_metadata=readme_source_metadata,
            payload=(
                self._read_json_artifact(
                    self.artifact_payload_repository.get_text_artifact(
                        record.github_repository_id,
                        RepositoryArtifactKind.ANALYSIS_RESULT,
                    )
                )
                if analysis_artifact is not None
                else None
            ),
        )

        return RepositoryExplorationResponse(
            github_repository_id=record.github_repository_id,
            source_provider=record.source_provider,
            owner_login=record.owner_login,
            repository_name=record.repository_name,
            full_name=record.full_name,
            repository_description=record.repository_description,
            discovery_source=record.discovery_source,
            firehose_discovery_mode=record.firehose_discovery_mode,
            intake_status=record.intake_status,
            triage_status=record.triage_status,
            analysis_status=record.analysis_status,
            stargazers_count=record.stargazers_count,
            forks_count=record.forks_count,
            github_created_at=record.github_created_at,
            discovered_at=record.discovered_at,
            status_updated_at=record.status_updated_at,
            pushed_at=record.pushed_at,
            category=record.category,
            agent_tags=record.agent_tags,
            triage=RepositoryTriageContextResponse(
                triage_status=record.triage.triage_status,
                triaged_at=record.triage.triaged_at,
                explanation=explanation,
            ),
            analysis_summary=analysis_summary,
            readme_snapshot=readme_snapshot,
            analysis_artifact=analysis_artifact_response,
            artifacts=artifact_responses,
            processing=RepositoryProcessingContextResponse(
                intake_created_at=record.processing.intake_created_at,
                intake_started_at=record.processing.intake_started_at,
                intake_completed_at=record.processing.intake_completed_at,
                intake_failed_at=record.processing.intake_failed_at,
                triaged_at=record.processing.triaged_at,
                analysis_started_at=record.processing.analysis_started_at,
                analysis_completed_at=record.processing.analysis_completed_at,
                analysis_last_attempted_at=record.processing.analysis_last_attempted_at,
                analysis_failed_at=record.processing.analysis_failed_at,
                failure=(
                    RepositoryFailureContextResponse(
                        stage=record.processing.failure.stage,
                        step=record.processing.failure.step,
                        upstream_source=record.processing.failure.upstream_source,
                        error_code=record.processing.failure.error_code,
                        error_message=record.processing.failure.error_message,
                        failed_at=record.processing.failure.failed_at,
                    )
                    if record.processing.failure is not None
                    else None
                ),
            ),
            has_readme_artifact=RepositoryArtifactKind.README_SNAPSHOT in artifact_kinds,
            has_analysis_artifact=RepositoryArtifactKind.ANALYSIS_RESULT in artifact_kinds,
            is_starred=record.is_starred,
            user_tags=record.user_tags,
            idea_family_ids=record.idea_family_ids,
        )

    def list_repository_catalog(
        self,
        params: RepositoryCatalogQueryParams,
    ) -> RepositoryCatalogPageResponse:
        page = self.repository.list_repository_catalog(
            RepositoryCatalogListParams(
                page=params.page,
                page_size=params.page_size,
                search=params.search,
                discovery_source=params.discovery_source,
                queue_status=params.queue_status,
                triage_status=params.triage_status,
                analysis_status=params.analysis_status,
                has_failures=params.has_failures,
                category=params.category,
                agent_tag=params.agent_tag,
                monetization_potential=params.monetization_potential,
                min_stars=params.min_stars,
                max_stars=params.max_stars,
                starred_only=params.starred_only,
                user_tag=params.user_tag,
                idea_family_id=params.idea_family_id,
                idea_search_id=params.idea_search_id,
                sort_by=params.sort_by.value,
                sort_order=params.sort_order.value,
            )
        )

        return RepositoryCatalogPageResponse(
            items=[
                RepositoryCatalogItemResponse(
                    github_repository_id=item.github_repository_id,
                    full_name=item.full_name,
                    owner_login=item.owner_login,
                    repository_name=item.repository_name,
                    repository_description=item.repository_description,
                    stargazers_count=item.stargazers_count,
                    forks_count=item.forks_count,
                    pushed_at=item.pushed_at,
                    discovery_source=item.discovery_source,
                    firehose_discovery_mode=item.firehose_discovery_mode,
                    intake_status=item.intake_status,
                    triage_status=item.triage_status,
                    analysis_status=item.analysis_status,
                    queue_created_at=item.queue_created_at,
                    processing_started_at=item.processing_started_at,
                    processing_completed_at=item.processing_completed_at,
                    intake_failed_at=item.intake_failed_at,
                    analysis_failed_at=item.analysis_failed_at,
                    failure=(
                        RepositoryFailureContextResponse(
                            stage=item.failure.stage,
                            step=item.failure.step,
                            upstream_source=item.failure.upstream_source,
                            error_code=item.failure.error_code,
                            error_message=item.failure.error_message,
                            failed_at=item.failure.failed_at,
                        )
                        if item.failure is not None
                        else None
                    ),
                    category=item.category,
                    category_confidence_score=item.category_confidence_score,
                    confidence_score=item.confidence_score,
                    analysis_outcome=item.analysis_outcome,
                    agent_tags=item.agent_tags,
                    suggested_new_tags=item.suggested_new_tags,
                    monetization_potential=item.monetization_potential,
                    has_readme_artifact=item.has_readme_artifact,
                    has_analysis_artifact=item.has_analysis_artifact,
                    is_starred=item.is_starred,
                    user_tags=item.user_tags,
                    idea_family_ids=item.idea_family_ids,
                )
                for item in page.items
            ],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
        )

    def get_repository_backlog_summary(self) -> RepositoryBacklogSummaryResponse:
        summary = self.repository.get_repository_backlog_summary()
        return RepositoryBacklogSummaryResponse(
            queue=RepositoryProcessingQueueSummaryResponse(**summary.queue),
            triage=RepositoryProcessingTriageSummaryResponse(**summary.triage),
            analysis=RepositoryProcessingAnalysisSummaryResponse(**summary.analysis),
        )

    def _read_json_artifact(self, raw: str | None) -> dict[str, object] | None:
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _get_str_metadata(metadata: dict[str, object], key: str) -> str | None:
        value = metadata.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _get_int_metadata(metadata: dict[str, object], key: str) -> int | None:
        value = metadata.get(key)
        return value if isinstance(value, int) else None

    @staticmethod
    def _get_dict_metadata(metadata: dict[str, object], key: str) -> dict[str, object]:
        value = metadata.get(key)
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _get_int_dict_metadata(metadata: dict[str, object], key: str) -> dict[str, int]:
        value = metadata.get(key)
        if not isinstance(value, dict):
            return {}
        return {
            raw_key: raw_value
            for raw_key, raw_value in value.items()
            if isinstance(raw_key, str) and isinstance(raw_value, int) and not isinstance(raw_value, bool)
        }

    @staticmethod
    def _get_str_list_metadata(metadata: dict[str, object], key: str) -> list[str]:
        value = metadata.get(key)
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    @classmethod
    def _coalesce_int_metadata(
        cls,
        primary_metadata: dict[str, object],
        fallback_metadata: dict[str, object],
        key: str,
    ) -> int | None:
        primary = cls._get_int_metadata(primary_metadata, key)
        if primary is not None:
            return primary
        return cls._get_int_metadata(fallback_metadata, key)
