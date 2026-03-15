from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlmodel import Session

from app.core.config import settings
from app.models import RepositoryArtifact, RepositoryArtifactPayload
from app.schemas.agent_event import ArtifactStorageStatusResponse


class ArtifactStorageStatusService:
    def __init__(self, session: Session, *, runtime_dir: Path | None = None) -> None:
        self.session = session
        self.runtime_dir = runtime_dir

    def get_status(self) -> ArtifactStorageStatusResponse:
        artifact_metadata_count = self._count_rows(RepositoryArtifact)
        artifact_payload_count = self._count_rows(RepositoryArtifactPayload)
        missing_payload_count = max(artifact_metadata_count - artifact_payload_count, 0)
        payload_coverage_ratio = (
            1.0 if artifact_metadata_count == 0 else artifact_payload_count / artifact_metadata_count
        )
        payload_coverage_percent = int(round(payload_coverage_ratio * 100))

        legacy_readme_file_count = self._count_legacy_files("data/readmes", "*.md")
        legacy_analysis_file_count = self._count_legacy_files("data/analyses", "*.json")
        legacy_file_count = legacy_readme_file_count + legacy_analysis_file_count

        safe_to_prune_legacy_files = (
            not settings.ARTIFACT_DEBUG_MIRROR and missing_payload_count == 0 and artifact_metadata_count > 0
        )
        if settings.ARTIFACT_DEBUG_MIRROR:
            prune_readiness_reason = (
                "Legacy files are still configured as a debug mirror. Turn off ARTIFACT_DEBUG_MIRROR first."
            )
        elif missing_payload_count > 0:
            prune_readiness_reason = (
                f"{missing_payload_count} artifact payloads are still missing from SQLite."
            )
        elif artifact_metadata_count == 0:
            prune_readiness_reason = "No repository artifacts are registered yet."
        else:
            prune_readiness_reason = (
                "All registered artifact metadata rows have DB payloads and debug mirroring is off."
            )

        return ArtifactStorageStatusResponse(
            artifact_metadata_count=artifact_metadata_count,
            artifact_payload_count=artifact_payload_count,
            missing_payload_count=missing_payload_count,
            payload_coverage_ratio=payload_coverage_ratio,
            payload_coverage_percent=payload_coverage_percent,
            legacy_readme_file_count=legacy_readme_file_count,
            legacy_analysis_file_count=legacy_analysis_file_count,
            legacy_file_count=legacy_file_count,
            artifact_debug_mirror_enabled=settings.ARTIFACT_DEBUG_MIRROR,
            safe_to_prune_legacy_files=safe_to_prune_legacy_files,
            prune_readiness_reason=prune_readiness_reason,
        )

    def _count_legacy_files(self, relative_dir: str, pattern: str) -> int:
        if self.runtime_dir is None:
            return 0
        artifact_dir = self.runtime_dir / relative_dir
        if not artifact_dir.is_dir():
            return 0
        return sum(1 for _ in artifact_dir.glob(pattern))

    def _count_rows(self, model: type[RepositoryArtifact] | type[RepositoryArtifactPayload]) -> int:
        row = self.session.exec(select(func.count()).select_from(model)).one()
        return int(row[0] if hasattr(row, "__getitem__") else row)
