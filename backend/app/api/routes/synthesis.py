from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_synthesis_service
from app.core.errors import AppError
from app.models.repository import SynthesisRunStatus
from app.schemas.synthesis import SynthesisRunResponse, CombinerTriggerRequest, DeepSynthesisTriggerRequest
from app.services.synthesis_service import SynthesisService

router = APIRouter()


@router.post("/combiner", response_model=SynthesisRunResponse, status_code=status.HTTP_201_CREATED)
def trigger_combiner(
    request: CombinerTriggerRequest,
    service: SynthesisService = Depends(get_synthesis_service),
):
    # Validate no duplicate repository IDs (only if repository_ids provided)
    if request.repository_ids and len(request.repository_ids) != len(set(request.repository_ids)):
        raise AppError(
            message="Duplicate repository IDs are not allowed in synthesis requests",
            code="DUPLICATE_REPOSITORIES",
            status_code=400
        )
    return service.trigger_combiner(request.idea_family_id, request.repository_ids)


@router.post("/deep-synthesis", response_model=SynthesisRunResponse, status_code=status.HTTP_201_CREATED)
def trigger_deep_synthesis(
    request: DeepSynthesisTriggerRequest,
    service: SynthesisService = Depends(get_synthesis_service),
) -> SynthesisRunResponse:
    return service.trigger_deep_synthesis(request.idea_family_id)


@router.get("/runs", response_model=list[SynthesisRunResponse])
def list_runs(
    idea_family_id: int | None = Query(default=None),
    status: SynthesisRunStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    repository_id: int | None = Query(default=None),
    service: SynthesisService = Depends(get_synthesis_service),
):
    return service.list_runs(idea_family_id, status, search, date_from, date_to, repository_id)


@router.get("/runs/{run_id}", response_model=SynthesisRunResponse)
def get_run(
    run_id: int,
    service: SynthesisService = Depends(get_synthesis_service),
) -> SynthesisRunResponse:
    return service.get_run(run_id)
