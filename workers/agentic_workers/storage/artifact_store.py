from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from agentic_workers.storage.backend_models import RepositoryArtifactKind


@dataclass(frozen=True, slots=True)
class RepositoryArtifactPayload:
    artifact_kind: RepositoryArtifactKind
    runtime_relative_path: str
    content_bytes: bytes
    content_sha256: str
    byte_size: int
    content_type: str
    source_kind: str
    source_url: str | None
    provenance_metadata: dict[str, object]
    generated_at: datetime


@dataclass(slots=True)
class _ActivatedArtifact:
    payload: RepositoryArtifactPayload
    final_path: Path
    temp_path: Path
    backup_path: Path | None = None


@dataclass(slots=True)
class ActivatedArtifactBundle:
    artifacts: list[_ActivatedArtifact]

    def rollback(self) -> None:
        for artifact in reversed(self.artifacts):
            if artifact.final_path.exists():
                artifact.final_path.unlink()
            if artifact.backup_path is not None and artifact.backup_path.exists():
                artifact.backup_path.replace(artifact.final_path)
            if artifact.temp_path.exists():
                artifact.temp_path.unlink()

    def finalize(self) -> None:
        for artifact in self.artifacts:
            if artifact.backup_path is not None and artifact.backup_path.exists():
                artifact.backup_path.unlink()
            if artifact.temp_path.exists():
                artifact.temp_path.unlink()


def build_text_artifact(
    *,
    runtime_relative_path: str,
    artifact_kind: RepositoryArtifactKind,
    content: str,
    content_type: str,
    source_kind: str,
    source_url: str | None,
    provenance_metadata: dict[str, object],
    generated_at: datetime,
) -> RepositoryArtifactPayload:
    content_bytes = content.encode("utf-8")
    return RepositoryArtifactPayload(
        artifact_kind=artifact_kind,
        runtime_relative_path=runtime_relative_path,
        content_bytes=content_bytes,
        content_sha256=sha256(content_bytes).hexdigest(),
        byte_size=len(content_bytes),
        content_type=content_type,
        source_kind=source_kind,
        source_url=source_url,
        provenance_metadata=dict(provenance_metadata),
        generated_at=generated_at,
    )


def build_json_artifact(
    *,
    runtime_relative_path: str,
    artifact_kind: RepositoryArtifactKind,
    payload: dict[str, object],
    source_kind: str,
    source_url: str | None,
    provenance_metadata: dict[str, object],
    generated_at: datetime,
) -> RepositoryArtifactPayload:
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return build_text_artifact(
        runtime_relative_path=runtime_relative_path,
        artifact_kind=artifact_kind,
        content=content,
        content_type="application/json",
        source_kind=source_kind,
        source_url=source_url,
        provenance_metadata=provenance_metadata,
        generated_at=generated_at,
    )


def activate_repository_artifacts(
    *,
    runtime_dir: Path,
    artifacts: list[RepositoryArtifactPayload],
) -> ActivatedArtifactBundle:
    activated: list[_ActivatedArtifact] = []
    current_artifact: _ActivatedArtifact | None = None
    try:
        for payload in artifacts:
            final_path = runtime_dir / payload.runtime_relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = final_path.with_name(f"{final_path.name}.tmp-{uuid4().hex}")
            temp_path.write_bytes(payload.content_bytes)

            current_artifact = _ActivatedArtifact(
                payload=payload,
                final_path=final_path,
                temp_path=temp_path,
            )
            if final_path.exists():
                backup_path = final_path.with_name(f"{final_path.name}.bak-{uuid4().hex}")
                final_path.replace(backup_path)
                current_artifact.backup_path = backup_path
            temp_path.replace(final_path)
            activated.append(current_artifact)
            current_artifact = None
    except Exception:
        if current_artifact is not None and current_artifact.temp_path.exists():
            current_artifact.temp_path.unlink()
        if (
            current_artifact is not None
            and current_artifact.backup_path is not None
            and current_artifact.backup_path.exists()
        ):
            current_artifact.backup_path.replace(current_artifact.final_path)
        ActivatedArtifactBundle(activated).rollback()
        raise
    return ActivatedArtifactBundle(activated)
