from __future__ import annotations

from app.repositories.repository_curation_repository import RepositoryCurationRepository
from app.schemas.repository_curation import (
    RepositoryCurationResponse,
    RepositoryUserTagResponse,
)


class RepositoryCurationService:
    def __init__(self, repository: RepositoryCurationRepository) -> None:
        self.repository = repository

    def get_repository_curation(self, github_repository_id: int) -> RepositoryCurationResponse:
        curation = self.repository.get_curation(github_repository_id)
        tags = self.repository.list_user_tags(github_repository_id)
        return RepositoryCurationResponse(
            is_starred=curation.is_starred if curation is not None else False,
            starred_at=curation.starred_at if curation is not None else None,
            user_tags=[tag.tag_label for tag in tags],
        )

    def set_repository_starred(
        self,
        github_repository_id: int,
        starred: bool,
    ) -> RepositoryCurationResponse:
        curation = self.repository.set_starred(github_repository_id, starred)
        tags = self.repository.list_user_tags(github_repository_id)
        return RepositoryCurationResponse(
            is_starred=curation.is_starred,
            starred_at=curation.starred_at,
            user_tags=[tag.tag_label for tag in tags],
        )

    def add_repository_user_tag(
        self,
        github_repository_id: int,
        tag_label: str,
    ) -> RepositoryUserTagResponse:
        tag = self.repository.add_user_tag(github_repository_id, tag_label)
        return RepositoryUserTagResponse(
            tag_label=tag.tag_label,
            created_at=tag.created_at,
        )

    def remove_repository_user_tag(self, github_repository_id: int, tag_label: str) -> None:
        self.repository.remove_user_tag(github_repository_id, tag_label)
