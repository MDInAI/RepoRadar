from __future__ import annotations

from datetime import datetime

from agentic_workers.storage.artifact_store import (
    RepositoryArtifactPayload,
    build_text_artifact,
)
from agentic_workers.storage.backend_models import RepositoryArtifactKind


def build_readme_artifact(
    *,
    github_repository_id: int,
    content: str,
    source_url: str,
    normalization_version: str,
    raw_character_count: int,
    normalized_character_count: int,
    removed_line_count: int,
    generated_at: datetime,
) -> RepositoryArtifactPayload:
    return build_text_artifact(
        runtime_relative_path=f"data/readmes/{github_repository_id}.md",
        artifact_kind=RepositoryArtifactKind.README_SNAPSHOT,
        content=content,
        content_type="text/markdown; charset=utf-8",
        source_kind="repository_readme",
        source_url=source_url,
        provenance_metadata={
            "normalization_version": normalization_version,
            "raw_character_count": raw_character_count,
            "normalized_character_count": normalized_character_count,
            "removed_line_count": removed_line_count,
        },
        generated_at=generated_at,
    )
