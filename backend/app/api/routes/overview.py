from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.schemas.overview import OverviewSummaryResponse
from app.services.overview_service import OverviewService

router = APIRouter()


@router.get("/overview/summary", response_model=OverviewSummaryResponse)
def get_overview_summary(
    session: Session = Depends(get_db_session),
) -> OverviewSummaryResponse:
    service = OverviewService(session)
    return service.get_summary()
