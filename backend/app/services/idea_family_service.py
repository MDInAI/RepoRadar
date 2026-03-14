from app.repositories.idea_family_repository import IdeaFamilyRepository, IdeaFamilyRecord
from app.schemas.idea_family import IdeaFamilyResponse, IdeaFamilyDetailResponse


class IdeaFamilyService:
    def __init__(self, repo: IdeaFamilyRepository):
        self._repo = repo

    def create_family(self, title: str, description: str | None) -> IdeaFamilyResponse:
        self._validate_title(title)
        record = self._repo.create_family(title, description)
        return self._to_response(record, member_count=0)

    def get_family(self, family_id: int) -> IdeaFamilyResponse:
        record = self._repo.get_family(family_id)
        if not record:
            from app.core.errors import AppError
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )

        member_count = len(self._repo.list_family_repositories(family_id))
        return self._to_response(record, member_count)

    def get_family_detail(self, family_id: int) -> IdeaFamilyDetailResponse:
        record = self._repo.get_family(family_id)
        if not record:
            from app.core.errors import AppError
            raise AppError(
                message=f"Idea family {family_id} not found",
                code="idea_family_not_found",
                status_code=404,
            )

        member_ids = self._repo.list_family_repositories(family_id)
        return IdeaFamilyDetailResponse(
            id=record.id,
            title=record.title,
            description=record.description,
            member_count=len(member_ids),
            member_repository_ids=member_ids,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def list_families(self) -> list[IdeaFamilyResponse]:
        records = self._repo.list_families()
        if not records:
            return []

        family_ids = [r.id for r in records]
        member_counts = self._repo.get_family_member_counts(family_ids)

        return [
            self._to_response(r, member_counts.get(r.id, 0))
            for r in records
        ]

    def update_family(
        self, family_id: int, title: str | None, description: str | None | object
    ) -> IdeaFamilyResponse:
        if title is not None:
            self._validate_title(title)
        record = self._repo.update_family(family_id, title, description)
        member_count = len(self._repo.list_family_repositories(family_id))
        return self._to_response(record, member_count)

    def delete_family(self, family_id: int) -> None:
        self._repo.delete_family(family_id)

    def add_repository(self, family_id: int, github_repository_id: int) -> None:
        self._repo.add_repository(family_id, github_repository_id)

    def remove_repository(self, family_id: int, github_repository_id: int) -> None:
        self._repo.remove_repository(family_id, github_repository_id)

    def _validate_title(self, title: str) -> None:
        if not title or not title.strip():
            from app.core.errors import AppError
            raise AppError(
                message="Title cannot be empty or whitespace-only",
                code="invalid_title",
                status_code=400,
            )

    def _to_response(self, record: IdeaFamilyRecord, member_count: int) -> IdeaFamilyResponse:
        return IdeaFamilyResponse(
            id=record.id,
            title=record.title,
            description=record.description,
            member_count=member_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
