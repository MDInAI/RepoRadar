from fastapi import APIRouter, Depends, status

from app.api.deps import get_idea_family_service
from app.schemas.idea_family import (
    IdeaFamilyResponse,
    IdeaFamilyDetailResponse,
    IdeaFamilyCreateRequest,
    IdeaFamilyUpdateRequest,
    IdeaFamilyMembershipRequest,
    BulkMembershipRequest,
    CreateFamilyFromSearchRequest,
    CreateFamilyFromSearchResponse,
)
from app.services.idea_family_service import IdeaFamilyService

router = APIRouter()


@router.get("/", response_model=list[IdeaFamilyResponse])
def list_families(
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> list[IdeaFamilyResponse]:
    return service.list_families()


@router.post("/", response_model=IdeaFamilyResponse, status_code=status.HTTP_201_CREATED)
def create_family(
    request: IdeaFamilyCreateRequest,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> IdeaFamilyResponse:
    return service.create_family(request.title, request.description)


@router.get("/{family_id}", response_model=IdeaFamilyDetailResponse)
def get_family(
    family_id: int,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> IdeaFamilyDetailResponse:
    return service.get_family_detail(family_id)


@router.put("/{family_id}", response_model=IdeaFamilyResponse)
def update_family(
    family_id: int,
    request: IdeaFamilyUpdateRequest,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> IdeaFamilyResponse:
    # Use ... (Ellipsis) sentinel to distinguish "field not provided" from "explicitly None"
    # - If description in request body → use that value (could be None to clear, or string to set)
    # - If description not in request body → use ... to signal "don't update this field"
    description = request.description if "description" in request.model_fields_set else ...
    return service.update_family(family_id, request.title, description)


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(
    family_id: int,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> None:
    service.delete_family(family_id)


@router.post("/{family_id}/members", status_code=status.HTTP_201_CREATED)
def add_repository(
    family_id: int,
    request: IdeaFamilyMembershipRequest,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> None:
    service.add_repository(family_id, request.github_repository_id)


@router.delete("/{family_id}/members/{github_repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_repository(
    family_id: int,
    github_repository_id: int,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> None:
    service.remove_repository(family_id, github_repository_id)


@router.post("/{family_id}/members/bulk")
def bulk_add_repositories(
    family_id: int,
    request: BulkMembershipRequest,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> dict:
    added_count = service.bulk_add_repositories(family_id, request.github_repository_ids)
    return {"added_count": added_count}


@router.post("/from-search", response_model=CreateFamilyFromSearchResponse, status_code=status.HTTP_201_CREATED)
def create_family_from_search(
    request: CreateFamilyFromSearchRequest,
    service: IdeaFamilyService = Depends(get_idea_family_service),
) -> CreateFamilyFromSearchResponse:
    return service.create_from_search(
        idea_search_id=request.idea_search_id,
        title=request.title,
        description=request.description,
        only_analyzed=request.only_analyzed,
    )
