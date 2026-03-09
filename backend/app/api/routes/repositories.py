from typing import TypeVar

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_repository_exploration_service, get_repository_triage_service
from app.core.errors import AppError
from app.models import (
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryMonetizationPotential,
    RepositoryTriageStatus,
)
from app.schemas.repository_exploration import (
    RepositoryCatalogPageResponse,
    RepositoryCatalogQueryParams,
    RepositoryCatalogSortBy,
    RepositoryCatalogSortOrder,
    RepositoryExplorationResponse,
)
from app.schemas.repository_triage import RepositoryTriageResponse
from app.services.repository_exploration_service import RepositoryExplorationService
from app.services.repository_triage_service import RepositoryTriageService

router = APIRouter(prefix="/repositories", tags=["repositories"])


TriageServiceDep = Depends(get_repository_triage_service)
ExplorationServiceDep = Depends(get_repository_exploration_service)
TEnum = TypeVar("TEnum")


def _parse_repository_catalog_enum(
    raw_value: str | None,
    enum_type: type[TEnum],
    field_name: str,
) -> TEnum | None:
    if raw_value is None or raw_value == "":
        return None

    try:
        return enum_type(raw_value)
    except ValueError as exc:
        raise AppError(
            message=f"Invalid value for {field_name}: {raw_value!r}.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={
                "field": field_name,
                "received": raw_value,
                "allowed": [item.value for item in enum_type],
            },
        ) from exc


def get_repository_catalog_query_params(
    page: int = Query(default=1),
    page_size: int = Query(default=30),
    search: str | None = Query(default=None),
    discovery_source: str | None = Query(default=None),
    triage_status: str | None = Query(default=None),
    analysis_status: str | None = Query(default=None),
    monetization_potential: str | None = Query(default=None),
    min_stars: int | None = Query(default=None),
    max_stars: int | None = Query(default=None),
    sort_by: str = Query(default=RepositoryCatalogSortBy.STARS.value),
    sort_order: str = Query(default=RepositoryCatalogSortOrder.DESC.value),
) -> RepositoryCatalogQueryParams:
    if page < 1:
        raise AppError(
            message="page must be greater than or equal to 1.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={"field": "page", "received": page},
        )
    if page_size < 1 or page_size > 100:
        raise AppError(
            message="page_size must be between 1 and 100.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={"field": "page_size", "received": page_size, "max": 100},
        )
    if min_stars is not None and min_stars < 0:
        raise AppError(
            message="min_stars must be greater than or equal to 0.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={"field": "min_stars", "received": min_stars},
        )
    if max_stars is not None and max_stars < 0:
        raise AppError(
            message="max_stars must be greater than or equal to 0.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={"field": "max_stars", "received": max_stars},
        )
    if min_stars is not None and max_stars is not None and max_stars < min_stars:
        raise AppError(
            message="max_stars must be greater than or equal to min_stars.",
            code="invalid_repository_catalog_query",
            status_code=400,
            details={
                "field": "max_stars",
                "received": max_stars,
                "min_stars": min_stars,
            },
        )

    normalized_search = search.strip() if search else None

    return RepositoryCatalogQueryParams(
        page=page,
        page_size=page_size,
        search=normalized_search or None,
        discovery_source=_parse_repository_catalog_enum(
            discovery_source,
            RepositoryDiscoverySource,
            "discovery_source",
        ),
        triage_status=_parse_repository_catalog_enum(
            triage_status,
            RepositoryTriageStatus,
            "triage_status",
        ),
        analysis_status=_parse_repository_catalog_enum(
            analysis_status,
            RepositoryAnalysisStatus,
            "analysis_status",
        ),
        monetization_potential=_parse_repository_catalog_enum(
            monetization_potential,
            RepositoryMonetizationPotential,
            "monetization_potential",
        ),
        min_stars=min_stars,
        max_stars=max_stars,
        sort_by=_parse_repository_catalog_enum(sort_by, RepositoryCatalogSortBy, "sort_by")
        or RepositoryCatalogSortBy.STARS,
        sort_order=_parse_repository_catalog_enum(
            sort_order,
            RepositoryCatalogSortOrder,
            "sort_order",
        )
        or RepositoryCatalogSortOrder.DESC,
    )


CatalogQueryParamsDep = Depends(get_repository_catalog_query_params)


@router.get("", response_model=RepositoryCatalogPageResponse)
def list_repository_catalog(
    params: RepositoryCatalogQueryParams = CatalogQueryParamsDep,
    service: RepositoryExplorationService = ExplorationServiceDep,
) -> RepositoryCatalogPageResponse:
    """Expose the paginated repository exploration catalog."""
    return service.list_repository_catalog(params)


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
