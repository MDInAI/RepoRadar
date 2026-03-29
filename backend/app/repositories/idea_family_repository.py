from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from app.models.repository import (
    IdeaFamily,
    IdeaFamilyMembership,
    IdeaSearchDiscovery,
    RepositoryAnalysisStatus,
    RepositoryIntake,
)
from app.core.errors import AppError


@dataclass(frozen=True)
class IdeaFamilyRecord:
    id: int
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class IdeaFamilyMembershipRecord:
    id: int
    idea_family_id: int
    github_repository_id: int
    added_at: datetime


class IdeaFamilyRepository:
    def __init__(self, session: Session):
        self._session = session

    def create_family(self, title: str, description: str | None) -> IdeaFamilyRecord:
        family = IdeaFamily(title=title, description=description)
        self._session.add(family)
        self._session.flush()
        return IdeaFamilyRecord(
            id=family.id,
            title=family.title,
            description=family.description,
            created_at=family.created_at,
            updated_at=family.updated_at,
        )

    def get_family(self, family_id: int) -> IdeaFamilyRecord | None:
        family = self._session.get(IdeaFamily, family_id)
        if not family:
            return None
        return IdeaFamilyRecord(
            id=family.id,
            title=family.title,
            description=family.description,
            created_at=family.created_at,
            updated_at=family.updated_at,
        )

    def list_families(self) -> list[IdeaFamilyRecord]:
        stmt = select(IdeaFamily).order_by(IdeaFamily.created_at.desc())
        families = self._session.execute(stmt).scalars().all()
        return [
            IdeaFamilyRecord(
                id=f.id,
                title=f.title,
                description=f.description,
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
            for f in families
        ]

    def update_family(
        self, family_id: int, title: str | None, description: str | None | object
    ) -> IdeaFamilyRecord:
        family = self._session.get(IdeaFamily, family_id)
        if not family:
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )

        if title is not None:
            family.title = title
        if description is not ...:
            family.description = description

        family.updated_at = datetime.now(timezone.utc)
        self._session.flush()

        return IdeaFamilyRecord(
            id=family.id,
            title=family.title,
            description=family.description,
            created_at=family.created_at,
            updated_at=family.updated_at,
        )

    def delete_family(self, family_id: int) -> None:
        family = self._session.get(IdeaFamily, family_id)
        if not family:
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )
        self._session.delete(family)
        self._session.flush()

    def add_repository(
        self, family_id: int, github_repository_id: int
    ) -> IdeaFamilyMembershipRecord:
        # Validate family exists
        family = self._session.get(IdeaFamily, family_id)
        if not family:
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )

        # Validate repository exists
        repo = self._session.get(RepositoryIntake, github_repository_id)
        if not repo:
            raise AppError(
                message=f"Repository {github_repository_id} not found",
                code="repository_not_found",
                status_code=404,
            )

        # Check for duplicate
        stmt = select(IdeaFamilyMembership).where(
            IdeaFamilyMembership.idea_family_id == family_id,
            IdeaFamilyMembership.github_repository_id == github_repository_id,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()
        if existing:
            raise AppError(
                message=f"Repository {github_repository_id} already in family {family_id}",
                code="duplicate_family_membership",
                status_code=409,
            )

        membership = IdeaFamilyMembership(
            idea_family_id=family_id,
            github_repository_id=github_repository_id,
        )
        self._session.add(membership)
        self._session.flush()

        return IdeaFamilyMembershipRecord(
            id=membership.id,
            idea_family_id=membership.idea_family_id,
            github_repository_id=membership.github_repository_id,
            added_at=membership.added_at,
        )

    def remove_repository(self, family_id: int, github_repository_id: int) -> None:
        stmt = delete(IdeaFamilyMembership).where(
            IdeaFamilyMembership.idea_family_id == family_id,
            IdeaFamilyMembership.github_repository_id == github_repository_id,
        )
        result = self._session.execute(stmt)
        if result.rowcount == 0:
            raise AppError(
                message=f"Repository {github_repository_id} not in family {family_id}",
                code="membership_not_found",
                status_code=404,
            )
        self._session.flush()

    def list_family_repositories(self, family_id: int) -> list[int]:
        stmt = select(IdeaFamilyMembership.github_repository_id).where(
            IdeaFamilyMembership.idea_family_id == family_id
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_repository_families(self, github_repository_id: int) -> list[int]:
        stmt = select(IdeaFamilyMembership.idea_family_id).where(
            IdeaFamilyMembership.github_repository_id == github_repository_id
        )
        return list(self._session.execute(stmt).scalars().all())

    def bulk_add_repositories(self, family_id: int, github_repository_ids: list[int]) -> int:
        """Add multiple repositories to a family, skipping duplicates. Returns count added."""
        family = self._session.get(IdeaFamily, family_id)
        if not family:
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )

        # Fetch existing members to skip duplicates
        existing_stmt = select(IdeaFamilyMembership.github_repository_id).where(
            IdeaFamilyMembership.idea_family_id == family_id
        )
        existing_ids = set(self._session.execute(existing_stmt).scalars().all())

        new_ids = [rid for rid in github_repository_ids if rid not in existing_ids]
        if not new_ids:
            return 0

        now = datetime.now(timezone.utc)
        for repo_id in new_ids:
            self._session.add(
                IdeaFamilyMembership(
                    idea_family_id=family_id,
                    github_repository_id=repo_id,
                    added_at=now,
                )
            )
        self._session.flush()
        return len(new_ids)

    def get_search_discovery_repo_ids(
        self, idea_search_id: int, only_analyzed: bool = False
    ) -> list[int]:
        """Return github_repository_ids for all discoveries in a scout search."""
        stmt = select(IdeaSearchDiscovery.github_repository_id).where(
            IdeaSearchDiscovery.idea_search_id == idea_search_id
        )
        if only_analyzed:
            stmt = (
                select(IdeaSearchDiscovery.github_repository_id)
                .join(
                    RepositoryIntake,
                    IdeaSearchDiscovery.github_repository_id
                    == RepositoryIntake.github_repository_id,
                )
                .where(IdeaSearchDiscovery.idea_search_id == idea_search_id)
                .where(
                    RepositoryIntake.analysis_status == RepositoryAnalysisStatus.COMPLETED
                )
            )
        return list(self._session.execute(stmt).scalars().all())

    def get_family_member_counts(self, family_ids: list[int]) -> dict[int, int]:
        """Get member counts for multiple families in a single query."""
        if not family_ids:
            return {}

        stmt = (
            select(
                IdeaFamilyMembership.idea_family_id,
                func.count(IdeaFamilyMembership.github_repository_id).label("count")
            )
            .where(IdeaFamilyMembership.idea_family_id.in_(family_ids))
            .group_by(IdeaFamilyMembership.idea_family_id)
        )
        results = self._session.execute(stmt).all()
        return {row.idea_family_id: row.count for row in results}
