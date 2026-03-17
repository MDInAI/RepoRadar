from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_overlord_service
from app.schemas.overlord import OverlordPolicyResponse, OverlordSummaryResponse
from app.services.overlord_service import OverlordService

router = APIRouter()


@router.get("/overlord/summary", response_model=OverlordSummaryResponse)
def get_overlord_summary(
    service: OverlordService = Depends(get_overlord_service),
) -> OverlordSummaryResponse:
    return service.get_summary()


@router.get("/overlord/policy", response_model=OverlordPolicyResponse)
def get_overlord_policy(
    service: OverlordService = Depends(get_overlord_service),
) -> OverlordPolicyResponse:
    return service.get_policy()
