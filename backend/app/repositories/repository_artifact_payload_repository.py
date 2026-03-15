from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from app.models import RepositoryArtifact, RepositoryArtifactKind, RepositoryArtifactPayload

logger = logging.getLogger(__name__)


class RepositoryArtifactPayloadRepository:
    def __init__(self, session: Session, *, runtime_dir: Path | None = None) -> None:
        self.session = session
        self.runtime_dir = runtime_dir

    def get_text_artifact(self, github_repository_id: int, artifact_kind: RepositoryArtifactKind) -> str | None:
        payload = self.session.get(RepositoryArtifactPayload, (github_repository_id, artifact_kind))
        if payload is not None:
            return payload.content_text

        artifact = self.session.get(RepositoryArtifact, (github_repository_id, artifact_kind))
        if artifact is None:
            return None
        return self._read_legacy_text(artifact.runtime_relative_path)

    def upsert_text_artifact(
        self,
        github_repository_id: int,
        artifact_kind: RepositoryArtifactKind,
        *,
        content_text: str,
        updated_at: datetime,
        content_encoding: str = "utf-8",
    ) -> None:
        values = {
            "github_repository_id": github_repository_id,
            "artifact_kind": artifact_kind.value,
            "content_text": content_text,
            "content_encoding": content_encoding,
            "updated_at": updated_at,
        }
        update_values = {
            "content_text": content_text,
            "content_encoding": content_encoding,
            "updated_at": updated_at,
        }
        table = RepositoryArtifactPayload.__table__
        dialect_name = self.session.get_bind().dialect.name

        if dialect_name == "sqlite":
            statement = sqlite_insert(table).values(**values)
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.github_repository_id, table.c.artifact_kind],
                    set_=update_values,
                )
            )
            return

        if dialect_name == "postgresql":
            statement = postgresql_insert(table).values(**values)
            self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[table.c.github_repository_id, table.c.artifact_kind],
                    set_=update_values,
                )
            )
            return

        record = self.session.get(RepositoryArtifactPayload, (github_repository_id, artifact_kind))
        if record is None:
            record = RepositoryArtifactPayload(
                github_repository_id=github_repository_id,
                artifact_kind=artifact_kind,
                content_text=content_text,
                content_encoding=content_encoding,
                updated_at=updated_at,
            )
        else:
            record.content_text = content_text
            record.content_encoding = content_encoding
            record.updated_at = updated_at
        self.session.add(record)

    def delete_artifact(self, github_repository_id: int, artifact_kind: RepositoryArtifactKind) -> None:
        record = self.session.get(RepositoryArtifactPayload, (github_repository_id, artifact_kind))
        if record is not None:
            self.session.delete(record)

    def mirror_text_artifact(
        self,
        *,
        runtime_relative_path: str,
        content_text: str,
        content_encoding: str = "utf-8",
    ) -> None:
        if self.runtime_dir is None:
            return
        try:
            artifact_path = self.runtime_dir / runtime_relative_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(content_text, encoding=content_encoding)
        except OSError as exc:
            logger.warning("Artifact mirror write failed for %s: %s", runtime_relative_path, exc)

    def _read_legacy_text(self, runtime_relative_path: str) -> str | None:
        if self.runtime_dir is None:
            return None
        artifact_path = self.runtime_dir / runtime_relative_path
        if not artifact_path.is_file():
            return None
        try:
            return artifact_path.read_text(encoding="utf-8")
        except OSError:
            return None
