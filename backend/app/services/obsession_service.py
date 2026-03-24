from __future__ import annotations

from app.core.errors import AppError
from app.repositories.idea_scout_repository import IdeaScoutRepository
from app.repositories.obsession_repository import ObsessionRepository, ObsessionContextRecord
from app.repositories.idea_family_repository import IdeaFamilyRepository
from app.repositories.synthesis_repository import SynthesisRepository


class ObsessionService:
    def __init__(
        self,
        obsession_repo: ObsessionRepository,
        idea_family_repo: IdeaFamilyRepository,
        synthesis_repo: SynthesisRepository,
        idea_scout_repo: IdeaScoutRepository | None = None,
    ):
        self._obsession_repo = obsession_repo
        self._idea_family_repo = idea_family_repo
        self._synthesis_repo = synthesis_repo
        self._idea_scout_repo = idea_scout_repo

    def _validate_title(self, title: str | None) -> None:
        """Validate title is not blank after stripping whitespace."""
        if title is not None and not title.strip():
            raise AppError(
                message="Title cannot be blank",
                code="invalid_input",
                status_code=400,
            )

    def _validate_refresh_policy(self, refresh_policy: str | None) -> None:
        """Validate refresh policy is a valid enum value."""
        if refresh_policy is not None and refresh_policy not in ("manual", "daily", "weekly"):
            raise AppError(
                message="Invalid refresh policy",
                code="invalid_input",
                status_code=400,
            )

    def create_context(
        self,
        title: str,
        description: str | None,
        refresh_policy: str,
        idea_family_id: int | None = None,
        synthesis_run_id: int | None = None,
        idea_text: str | None = None,
    ) -> ObsessionContextRecord:
        # Validate exactly one target is provided
        targets_provided = sum([
            idea_family_id is not None,
            synthesis_run_id is not None,
            idea_text is not None and idea_text.strip() != "",
        ])
        if targets_provided != 1:
            raise AppError(
                message="Exactly one of idea_family_id, synthesis_run_id, or idea_text must be provided",
                code="invalid_input",
                status_code=400,
            )

        idea_search_id = None

        # Validate the target exists
        if idea_family_id is not None:
            family = self._idea_family_repo.get_family(idea_family_id)
            if not family:
                raise AppError(
                    message=f"Idea family {idea_family_id} not found",
                    code="idea_family_not_found",
                    status_code=404,
                )
        elif synthesis_run_id is not None:
            run = self._synthesis_repo.get_run(synthesis_run_id)
            if not run:
                raise AppError(
                    message=f"Synthesis run {synthesis_run_id} not found",
                    code="synthesis_run_not_found",
                    status_code=404,
                )
        elif idea_text is not None:
            # Create a forward-watching IdeaSearch for this obsession
            if self._idea_scout_repo is None:
                raise AppError(
                    message="IdeaScout repository is not available",
                    code="internal_error",
                    status_code=500,
                )
            from app.services.idea_scout_service import IdeaScoutService
            idea_scout_svc = IdeaScoutService(self._idea_scout_repo)
            search = idea_scout_svc.create_search(
                idea_text=idea_text.strip(),
                direction="forward",
            )
            idea_search_id = search.id

        self._validate_title(title)
        self._validate_refresh_policy(refresh_policy)

        return self._obsession_repo.create_context(
            title=title.strip(),
            description=description,
            refresh_policy=refresh_policy,
            idea_family_id=idea_family_id,
            synthesis_run_id=synthesis_run_id,
            idea_search_id=idea_search_id,
            idea_text=idea_text.strip() if idea_text else None,
        )

    def list_contexts(
        self, idea_family_id: int | None = None, status: str | None = None
    ) -> list[tuple[ObsessionContextRecord, int]]:
        """List contexts with their synthesis run counts."""
        contexts = self._obsession_repo.list_contexts(idea_family_id, status)
        context_ids = [c.id for c in contexts]
        counts = self._obsession_repo.get_synthesis_run_counts(context_ids) if context_ids else {}
        return [(c, counts.get(c.id, 0)) for c in contexts]

    def get_context_detail(self, context_id: int):
        """Get context with synthesis run history, family, and repository info."""
        context = self._obsession_repo.get_context(context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )
        runs = self._obsession_repo.get_synthesis_runs(context_id)
        memory_count = self._obsession_repo.get_memory_segment_count(context_id)

        # Get family title, repository details, and scope update time
        family_title = None
        repository_ids = []
        scope_updated_at = None
        if context.idea_family_id:
            family = self._idea_family_repo.get_family(context.idea_family_id)
            if family:
                family_title = family.title
                repository_ids = self._idea_family_repo.list_family_repositories(context.idea_family_id)
                scope_updated_at = family.updated_at
        elif context.synthesis_run_id:
            run = self._synthesis_repo.get_run(context.synthesis_run_id)
            if run:
                repository_ids = run.input_repository_ids
                scope_updated_at = run.created_at

        repositories = self._idea_family_repo.get_repositories_by_ids(repository_ids) if repository_ids else []

        return context, runs, family_title, repositories, scope_updated_at, memory_count

    def update_context(
        self,
        context_id: int,
        title: str | None,
        description: str | None | object,
        status: str | None,
        refresh_policy: str | None,
    ) -> tuple[ObsessionContextRecord, int]:
        """Update context metadata with validation, returns context and synthesis run count."""
        self._validate_title(title)
        self._validate_refresh_policy(refresh_policy)

        context = self._obsession_repo.update_context(
            context_id, title.strip() if title else None, description, status, refresh_policy
        )
        counts = self._obsession_repo.get_synthesis_run_counts([context.id])
        return context, counts.get(context.id, 0)

    def trigger_refresh(self, context_id: int, repository_ids: list[int]) -> int:
        context = self._obsession_repo.get_context(context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        # Wrap in transaction to ensure atomicity
        run = self._synthesis_repo.create_run(
            idea_family_id=context.idea_family_id,
            run_type="obsession",
            repository_ids=repository_ids,
            obsession_context_id=context_id,
        )
        self._obsession_repo.update_last_refresh(context_id)
        # Session commit happens at route handler level, ensuring both operations succeed or fail together

        return run.id

    def trigger_context_refresh(self, context_id: int) -> int:
        """Trigger refresh for a context, automatically loading repositories."""
        context = self._obsession_repo.get_context(context_id)
        if not context:
            raise AppError(
                message=f"Obsession context {context_id} not found",
                code="obsession_context_not_found",
                status_code=404,
            )

        # Get repositories from either family or synthesis run
        if context.idea_family_id is not None:
            repository_ids = self._idea_family_repo.list_family_repositories(context.idea_family_id)
        else:
            # Get repositories from the original synthesis run
            run = self._synthesis_repo.get_run(context.synthesis_run_id)
            repository_ids = run.input_repository_ids if run else []

        return self.trigger_refresh(context_id, repository_ids)
