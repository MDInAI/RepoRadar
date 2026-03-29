from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_idea_scout_service
from app.schemas.idea_scout import (
    DiscoveredRepoResponse,
    IdeaSearchCreateRequest,
    IdeaSearchDetailResponse,
    IdeaSearchProgressSummary,
    IdeaSearchResponse,
    IdeaSearchUpdateRequest,
)
from app.services.idea_scout_service import IdeaScoutService

router = APIRouter()


def _to_response(rec) -> IdeaSearchResponse:
    return IdeaSearchResponse(
        id=rec.id,
        idea_text=rec.idea_text,
        search_queries=rec.search_queries,
        direction=rec.direction,
        status=rec.status,
        obsession_context_id=rec.obsession_context_id,
        total_repos_found=rec.total_repos_found,
        analyst_enabled=rec.analyst_enabled,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


@router.post("/searches", response_model=IdeaSearchResponse, status_code=status.HTTP_201_CREATED)
def create_search(
    request: IdeaSearchCreateRequest,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    search = service.create_search(
        idea_text=request.idea_text,
        direction=request.direction,
    )
    return _to_response(search)


@router.get("/searches", response_model=list[IdeaSearchResponse])
def list_searches(
    search_status: str | None = Query(None, alias="status"),
    direction: str | None = Query(None),
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> list[IdeaSearchResponse]:
    searches = service.list_searches(status=search_status, direction=direction)
    return [_to_response(s) for s in searches]


@router.get("/searches/{search_id}", response_model=IdeaSearchDetailResponse)
def get_search(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchDetailResponse:
    search, progress, discovery_count = service.get_search_detail(search_id)
    analyzed_count = service._repo.get_analyzed_count(search_id)
    return IdeaSearchDetailResponse(
        id=search.id,
        idea_text=search.idea_text,
        search_queries=search.search_queries,
        direction=search.direction,
        status=search.status,
        obsession_context_id=search.obsession_context_id,
        total_repos_found=search.total_repos_found,
        analyst_enabled=search.analyst_enabled,
        progress=[
            IdeaSearchProgressSummary(
                query_index=p.query_index,
                window_start_date=str(p.window_start_date),
                created_before_boundary=str(p.created_before_boundary),
                exhausted=p.exhausted,
                resume_required=p.resume_required,
                next_page=p.next_page,
                pages_processed_in_run=p.pages_processed_in_run,
                last_checkpointed_at=p.last_checkpointed_at,
                consecutive_errors=p.consecutive_errors,
                last_error=p.last_error,
            )
            for p in progress
        ],
        discovery_count=discovery_count,
        analyzed_count=analyzed_count,
        created_at=search.created_at,
        updated_at=search.updated_at,
    )


@router.post("/searches/{search_id}/analyst/enable", response_model=IdeaSearchResponse)
def enable_analyst(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.set_analyst_enabled(search_id, True))


@router.post("/searches/{search_id}/analyst/disable", response_model=IdeaSearchResponse)
def disable_analyst(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.set_analyst_enabled(search_id, False))


@router.post("/searches/{search_id}/pause", response_model=IdeaSearchResponse)
def pause_search(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.pause_search(search_id))


@router.post("/searches/{search_id}/resume", response_model=IdeaSearchResponse)
def resume_search(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.resume_search(search_id))


@router.post("/searches/{search_id}/cancel", response_model=IdeaSearchResponse)
def cancel_search(
    search_id: int,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.cancel_search(search_id))


@router.put("/searches/{search_id}", response_model=IdeaSearchResponse)
def update_search(
    search_id: int,
    request: IdeaSearchUpdateRequest,
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> IdeaSearchResponse:
    return _to_response(service.update_search_queries(search_id, request.search_queries))


@router.get("/searches/{search_id}/discoveries", response_model=list[DiscoveredRepoResponse])
def list_discoveries(
    search_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: IdeaScoutService = Depends(get_idea_scout_service),
) -> list[DiscoveredRepoResponse]:
    discoveries = service.list_discoveries(search_id, limit=limit, offset=offset)
    return [
        DiscoveredRepoResponse(
            github_repository_id=d.github_repository_id,
            full_name=d.full_name,
            description=d.description,
            stargazers_count=d.stargazers_count,
            discovered_at=d.discovered_at,
        )
        for d in discoveries
    ]
