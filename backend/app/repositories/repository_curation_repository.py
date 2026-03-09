from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.errors import AppError
from app.models import RepositoryIntake, RepositoryUserCuration, RepositoryUserTag


@dataclass(frozen=True, slots=True)
class _RepositoryUserCurationRecord:
    github_repository_id: int
    is_starred: bool
    starred_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class _RepositoryUserTagRecord:
    tag_label: str
    created_at: datetime


class RepositoryCurationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_curation(self, github_repository_id: int) -> _RepositoryUserCurationRecord | None:
        self._require_repository_exists(github_repository_id)
        row = self.session.get(RepositoryUserCuration, github_repository_id)
        if row is None:
            return None
        return _RepositoryUserCurationRecord(
            github_repository_id=row.github_repository_id,
            is_starred=row.is_starred,
            starred_at=row.starred_at,
            updated_at=row.updated_at,
        )

    def set_starred(
        self,
        github_repository_id: int,
        starred: bool,
    ) -> _RepositoryUserCurationRecord:
        self._require_repository_exists(github_repository_id)
        now = datetime.now(timezone.utc)
        row = self.session.get(RepositoryUserCuration, github_repository_id)
        if row is None:
            row = RepositoryUserCuration(
                github_repository_id=github_repository_id,
            )
        row.is_starred = starred
        row.starred_at = now if starred else None
        row.updated_at = now
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _RepositoryUserCurationRecord(
            github_repository_id=row.github_repository_id,
            is_starred=row.is_starred,
            starred_at=row.starred_at,
            updated_at=row.updated_at,
        )

    def list_user_tags(self, github_repository_id: int) -> list[_RepositoryUserTagRecord]:
        self._require_repository_exists(github_repository_id)
        rows = self.session.exec(
            select(RepositoryUserTag)
            .where(RepositoryUserTag.github_repository_id == github_repository_id)
            .order_by(RepositoryUserTag.created_at.asc(), RepositoryUserTag.id.asc())
        ).all()
        return [
            _RepositoryUserTagRecord(
                tag_label=row.tag_label,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def add_user_tag(
        self,
        github_repository_id: int,
        tag_label: str,
    ) -> _RepositoryUserTagRecord:
        self._require_repository_exists(github_repository_id)
        existing = self.session.exec(
            select(RepositoryUserTag).where(
                RepositoryUserTag.github_repository_id == github_repository_id,
                RepositoryUserTag.tag_label == tag_label,
            )
        ).first()
        if existing is not None:
            raise AppError(
                message=f"Tag {tag_label!r} already exists for repository {github_repository_id}.",
                code="repository_user_tag_conflict",
                status_code=409,
                details={
                    "github_repository_id": github_repository_id,
                    "tag_label": tag_label,
                },
            )

        row = RepositoryUserTag(
            github_repository_id=github_repository_id,
            tag_label=tag_label,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _RepositoryUserTagRecord(
            tag_label=row.tag_label,
            created_at=row.created_at,
        )

    def remove_user_tag(self, github_repository_id: int, tag_label: str) -> None:
        self._require_repository_exists(github_repository_id)
        row = self.session.exec(
            select(RepositoryUserTag).where(
                RepositoryUserTag.github_repository_id == github_repository_id,
                RepositoryUserTag.tag_label == tag_label,
            )
        ).first()
        if row is None:
            return
        self.session.delete(row)
        self.session.commit()

    def _require_repository_exists(self, github_repository_id: int) -> None:
        intake = self.session.get(RepositoryIntake, github_repository_id)
        if intake is None:
            raise AppError(
                message=f"Repository {github_repository_id} was not found.",
                code="repository_not_found",
                status_code=404,
                details={"github_repository_id": github_repository_id},
            )
