from __future__ import annotations

from app.core.errors import AppError
from app.repositories.repository_triage_repository import RepositoryTriageRepository
from app.schemas.repository_triage import (
    RepositoryTriageExplanationResponse,
    RepositoryTriageResponse,
)


class RepositoryTriageService:
    def __init__(self, repository: RepositoryTriageRepository) -> None:
        self.repository = repository

    def get_repository_triage(self, github_repository_id: int) -> RepositoryTriageResponse:
        record = self.repository.get_repository_triage(github_repository_id)
        if record is None:
            raise AppError(
                message=f"Repository {github_repository_id} was not found.",
                code="repository_not_found",
                status_code=404,
                details={"github_repository_id": github_repository_id},
            )

        explanation = None
        if record.explanation is not None:
            explanation = RepositoryTriageExplanationResponse(
                kind=record.explanation.kind,
                summary=record.explanation.summary,
                matched_include_rules=record.explanation.matched_include_rules,
                matched_exclude_rules=record.explanation.matched_exclude_rules,
                explained_at=record.explanation.explained_at,
            )

        return RepositoryTriageResponse(
            triage_status=record.triage_status,
            triaged_at=record.triaged_at,
            explanation=explanation,
        )
