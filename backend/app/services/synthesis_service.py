from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.errors import AppError
from app.models import RepositoryIntake
from app.repositories.synthesis_repository import SynthesisRepository, SynthesisRunRecord
from app.repositories.idea_family_repository import IdeaFamilyRepository
from app.schemas.synthesis import SynthesisRunResponse


class SynthesisService:
    def __init__(self, synthesis_repo: SynthesisRepository, family_repo: IdeaFamilyRepository, session: Session):
        self._synthesis_repo = synthesis_repo
        self._family_repo = family_repo
        self._session = session

    def trigger_combiner(
        self, idea_family_id: int | None, repository_ids: list[int] | None
    ) -> SynthesisRunResponse:
        # Validate mutual exclusivity
        if idea_family_id is None and repository_ids is None:
            raise AppError(
                message="Either idea_family_id or repository_ids must be provided",
                code="invalid_input",
                status_code=400,
            )
        if idea_family_id is not None and repository_ids is not None:
            raise AppError(
                message="Cannot provide both idea_family_id and repository_ids",
                code="invalid_input",
                status_code=400,
            )

        # Resolve repository IDs
        if idea_family_id is not None:
            family = self._family_repo.get_family(idea_family_id)
            if not family:
                raise AppError(
                    message=f"Idea family {idea_family_id} not found",
                    code="idea_family_not_found",
                    status_code=404,
                )
            repository_ids = self._family_repo.list_family_repositories(idea_family_id)

        # Validate 2-3 repositories
        if not repository_ids or len(repository_ids) < 2 or len(repository_ids) > 3:
            raise AppError(
                message="Combiner requires 2-3 repositories",
                code="invalid_repository_count",
                status_code=400,
            )

        # Validate all repository IDs exist
        for repo_id in repository_ids:
            repo = self._session.get(RepositoryIntake, repo_id)
            if not repo:
                raise AppError(
                    message=f"Repository {repo_id} not found",
                    code="repository_not_found",
                    status_code=404,
                )

        # Create synthesis run
        record = self._synthesis_repo.create_run(idea_family_id, "combiner", repository_ids)

        # TODO: Enqueue worker task

        return self._to_response(record)

    def get_run(self, run_id: int) -> SynthesisRunResponse:
        record = self._synthesis_repo.get_run(run_id)
        if not record:
            raise AppError(
                message=f"Synthesis run {run_id} not found",
                code="synthesis_run_not_found",
                status_code=404,
            )
        return self._to_response(record)

    def list_runs(
        self,
        idea_family_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        repository_id: int | None = None,
    ) -> list[SynthesisRunResponse]:
        # Parse date strings to timezone-aware datetimes
        from_date = None
        to_date = None

        if date_from:
            try:
                parsed = datetime.fromisoformat(date_from)
                from_date = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                raise AppError(
                    message=f"Invalid date_from format: {date_from}",
                    code="INVALID_FILTER_PARAMETERS",
                    status_code=400
                )

        if date_to:
            try:
                parsed = datetime.fromisoformat(date_to)
                to_date = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                raise AppError(
                    message=f"Invalid date_to format: {date_to}",
                    code="INVALID_FILTER_PARAMETERS",
                    status_code=400
                )

        records = self._synthesis_repo.list_runs(
            idea_family_id=idea_family_id,
            status=status,
            search=search,
            date_from=from_date,
            date_to=to_date,
            repository_id=repository_id,
        )

        return [self._to_response(r) for r in records]

    def _to_response(self, record: SynthesisRunRecord) -> SynthesisRunResponse:
        return SynthesisRunResponse(
            id=record.id,
            idea_family_id=record.idea_family_id,
            obsession_context_id=record.obsession_context_id,
            run_type=record.run_type,
            status=record.status,
            input_repository_ids=record.input_repository_ids,
            output_text=record.output_text,
            title=record.title,
            summary=record.summary,
            key_insights=record.key_insights,
            error_message=record.error_message,
            started_at=record.started_at,
            completed_at=record.completed_at,
            created_at=record.created_at,
        )
