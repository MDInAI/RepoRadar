from fastapi import APIRouter, Depends

from app.api.deps import get_repository_exploration_service, get_repository_triage_service
from app.schemas.repository_exploration import RepositoryExplorationResponse
from app.schemas.repository_triage import RepositoryTriageResponse
from app.services.repository_exploration_service import RepositoryExplorationService
from app.services.repository_triage_service import RepositoryTriageService

router = APIRouter(prefix="/repositories", tags=["repositories"])


TriageServiceDep = Depends(get_repository_triage_service)
ExplorationServiceDep = Depends(get_repository_exploration_service)


@router.get("/{github_repository_id}/triage", response_model=RepositoryTriageResponse)
def read_repository_triage(
    github_repository_id: int,
    service: RepositoryTriageService = TriageServiceDep,
) -> RepositoryTriageResponse:
    """Expose the stored repository triage status and explanation snapshot."""
    return service.get_repository_triage(github_repository_id)


@router.get("/{github_repository_id}", response_model=RepositoryExplorationResponse)
def read_repository_exploration(
    github_repository_id: int,
    service: RepositoryExplorationService = ExplorationServiceDep,
) -> RepositoryExplorationResponse:
    """Expose the full repository exploration context, including artifacts and analysis."""
    return service.get_repository_exploration(github_repository_id)
