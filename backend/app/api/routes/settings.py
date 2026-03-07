from fastapi import APIRouter, Depends

from app.schemas.settings import SettingsSummaryResponse
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def get_settings_service() -> SettingsService:
    return SettingsService()


ServiceDep = Depends(get_settings_service)


@router.get("/summary", response_model=SettingsSummaryResponse)
def read_settings_summary(
    service: SettingsService = ServiceDep,
) -> SettingsSummaryResponse:
    """Expose backend-owned configuration ownership and validation summaries."""
    return service.get_settings_summary()
