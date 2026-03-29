from fastapi import APIRouter, Depends, status, Query

from app.api.deps import get_obsession_service
from app.schemas.obsession import (
    ObsessionContextResponse,
    ObsessionContextDetailResponse,
    ObsessionContextCreateRequest,
    ObsessionContextUpdateRequest,
    SynthesisRunSummary,
)
from app.services.obsession_service import ObsessionService

router = APIRouter()


@router.post("/contexts", response_model=ObsessionContextResponse, status_code=status.HTTP_201_CREATED)
def create_context(
    request: ObsessionContextCreateRequest,
    service: ObsessionService = Depends(get_obsession_service),
) -> ObsessionContextResponse:
    context = service.create_context(
        title=request.title,
        description=request.description,
        refresh_policy=request.refresh_policy,
        idea_family_id=request.idea_family_id,
        synthesis_run_id=request.synthesis_run_id,
        idea_search_id=request.idea_search_id,
        idea_text=request.idea_text,
    )
    return ObsessionContextResponse(
        id=context.id,
        idea_family_id=context.idea_family_id,
        synthesis_run_id=context.synthesis_run_id,
        idea_search_id=context.idea_search_id,
        idea_text=context.idea_text,
        title=context.title,
        description=context.description,
        status=context.status,
        refresh_policy=context.refresh_policy,
        last_refresh_at=context.last_refresh_at,
        synthesis_run_count=0,
        created_at=context.created_at,
        updated_at=context.updated_at,
    )


@router.get("/contexts", response_model=list[ObsessionContextResponse])
def list_contexts(
    idea_family_id: int | None = Query(None),
    status: str | None = Query(None),
    service: ObsessionService = Depends(get_obsession_service),
) -> list[ObsessionContextResponse]:
    contexts_with_counts = service.list_contexts(idea_family_id, status)
    return [
        ObsessionContextResponse(
            id=c.id,
            idea_family_id=c.idea_family_id,
            synthesis_run_id=c.synthesis_run_id,
            idea_search_id=c.idea_search_id,
            idea_text=c.idea_text,
            title=c.title,
            description=c.description,
            status=c.status,
            refresh_policy=c.refresh_policy,
            last_refresh_at=c.last_refresh_at,
            synthesis_run_count=count,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c, count in contexts_with_counts
    ]


@router.get("/contexts/{context_id}", response_model=ObsessionContextDetailResponse)
def get_context(
    context_id: int,
    service: ObsessionService = Depends(get_obsession_service),
) -> ObsessionContextDetailResponse:
    from app.schemas.obsession import RepositorySummary
    context, runs, family_title, repositories, scope_updated_at, memory_count = service.get_context_detail(context_id)

    return ObsessionContextDetailResponse(
        id=context.id,
        idea_family_id=context.idea_family_id,
        synthesis_run_id=context.synthesis_run_id,
        idea_search_id=context.idea_search_id,
        idea_text=context.idea_text,
        title=context.title,
        description=context.description,
        status=context.status,
        refresh_policy=context.refresh_policy,
        last_refresh_at=context.last_refresh_at,
        synthesis_runs=[
            SynthesisRunSummary(
                id=r.id,
                run_type=r.run_type,
                status=r.status,
                title=r.title,
                started_at=r.started_at,
                completed_at=r.completed_at,
                created_at=r.created_at,
            )
            for r in runs
        ],
        family_title=family_title,
        repository_count=len(repositories),
        repositories=[
            RepositorySummary(id=r.id, full_name=r.full_name, stars=r.stars)
            for r in repositories
        ],
        scope_updated_at=scope_updated_at,
        memory_segment_count=memory_count,
        created_at=context.created_at,
        updated_at=context.updated_at,
    )


@router.put("/contexts/{context_id}", response_model=ObsessionContextResponse)
def update_context(
    context_id: int,
    request: ObsessionContextUpdateRequest,
    service: ObsessionService = Depends(get_obsession_service),
) -> ObsessionContextResponse:
    description = request.description if "description" in request.model_fields_set else ...
    context, synthesis_run_count = service.update_context(
        context_id, request.title, description, request.status, request.refresh_policy
    )
    return ObsessionContextResponse(
        id=context.id,
        idea_family_id=context.idea_family_id,
        synthesis_run_id=context.synthesis_run_id,
        idea_search_id=context.idea_search_id,
        idea_text=context.idea_text,
        title=context.title,
        description=context.description,
        status=context.status,
        refresh_policy=context.refresh_policy,
        last_refresh_at=context.last_refresh_at,
        synthesis_run_count=synthesis_run_count,
        created_at=context.created_at,
        updated_at=context.updated_at,
    )


@router.post("/contexts/{context_id}/refresh", status_code=status.HTTP_201_CREATED)
def trigger_refresh(
    context_id: int,
    service: ObsessionService = Depends(get_obsession_service),
) -> dict[str, int]:
    run_id = service.trigger_context_refresh(context_id)
    return {"synthesis_run_id": run_id}
