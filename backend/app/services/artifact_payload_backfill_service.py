from __future__ import annotations

from dataclasses import dataclass
import logging

from sqlmodel import Session, select

from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from app.models import RepositoryArtifact, RepositoryArtifactPayload

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArtifactPayloadBackfillResult:
    scanned: int
    imported: int
    skipped_existing: int
    missing_legacy_file: int


class ArtifactPayloadBackfillService:
    def __init__(
        self,
        session: Session,
        artifact_payload_repository: RepositoryArtifactPayloadRepository,
    ) -> None:
        self.session = session
        self.artifact_payload_repository = artifact_payload_repository

    def backfill(self, *, limit: int | None = None) -> ArtifactPayloadBackfillResult:
        statement = select(RepositoryArtifact).order_by(
            RepositoryArtifact.github_repository_id,
            RepositoryArtifact.artifact_kind,
        )
        if limit is not None:
            statement = statement.limit(limit)

        scanned = 0
        imported = 0
        skipped_existing = 0
        missing_legacy_file = 0

        for artifact in self.session.exec(statement).all():
            scanned += 1
            payload = self.session.get(
                RepositoryArtifactPayload,
                (artifact.github_repository_id, artifact.artifact_kind),
            )
            if payload is not None:
                skipped_existing += 1
                continue

            content = self.artifact_payload_repository.get_text_artifact(
                artifact.github_repository_id,
                artifact.artifact_kind,
            )
            if content is None:
                missing_legacy_file += 1
                logger.warning(
                    "Skipping artifact payload import for repo=%s kind=%s; legacy file is missing.",
                    artifact.github_repository_id,
                    artifact.artifact_kind.value,
                )
                continue

            self.artifact_payload_repository.upsert_text_artifact(
                artifact.github_repository_id,
                artifact.artifact_kind,
                content_text=content,
                updated_at=artifact.generated_at,
            )
            imported += 1

        self.session.commit()
        return ArtifactPayloadBackfillResult(
            scanned=scanned,
            imported=imported,
            skipped_existing=skipped_existing,
            missing_legacy_file=missing_legacy_file,
        )
