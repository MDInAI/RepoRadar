from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from app.models import (
    RepositoryIntake,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)


@dataclass(frozen=True, slots=True)
class RepositoryTriageExplanationRecord:
    kind: RepositoryTriageExplanationKind
    summary: str
    matched_include_rules: list[str]
    matched_exclude_rules: list[str]
    explained_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryTriageRecord:
    triage_status: RepositoryTriageStatus
    triaged_at: datetime | None
    explanation: RepositoryTriageExplanationRecord | None


class RepositoryTriageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_repository_triage(self, github_repository_id: int) -> RepositoryTriageRecord | None:
        intake = self.session.get(RepositoryIntake, github_repository_id)
        if intake is None:
            return None

        explanation_row = self.session.get(RepositoryTriageExplanation, github_repository_id)
        explanation = None
        if explanation_row is not None:
            explanation = RepositoryTriageExplanationRecord(
                kind=explanation_row.explanation_kind,
                summary=explanation_row.explanation_summary,
                matched_include_rules=list(explanation_row.matched_include_rules),
                matched_exclude_rules=list(explanation_row.matched_exclude_rules),
                explained_at=explanation_row.explained_at,
            )

        return RepositoryTriageRecord(
            triage_status=intake.triage_status,
            triaged_at=intake.triaged_at,
            explanation=explanation,
        )
