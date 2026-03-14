from fastapi import APIRouter, Depends, Request

from app.api.deps import get_settings_service
from app.core.config import settings
from app.core.event_bridge_health import EventBridgeHealth
from app.core.event_broadcaster import EventBroadcaster
from app.schemas.settings import SettingsSummaryResponse
from app.schemas.settings import (
    EventBridgeRuntimeHealthResponse,
    EventStreamRuntimeResponse,
    SettingsRuntimeResponse,
)
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])

ServiceDep = Depends(get_settings_service)


@router.get("/summary", response_model=SettingsSummaryResponse)
def read_settings_summary(
    service: SettingsService = ServiceDep,
) -> SettingsSummaryResponse:
    """Expose backend-owned configuration ownership and validation summaries."""
    return service.get_settings_summary()


@router.get("/runtime", response_model=SettingsRuntimeResponse)
def read_settings_runtime(request: Request) -> SettingsRuntimeResponse:
    event_bridge_health = getattr(request.app.state, "event_bridge_health", None)
    event_broadcaster = getattr(request.app.state, "event_broadcaster", None)

    if isinstance(event_bridge_health, EventBridgeHealth):
        bridge_snapshot = event_bridge_health.snapshot()
    else:
        bridge_snapshot = EventBridgeHealth().snapshot()

    current_subscribers = (
        event_broadcaster.subscriber_count()
        if isinstance(event_broadcaster, EventBroadcaster)
        else 0
    )

    return SettingsRuntimeResponse(
        event_bridge=EventBridgeRuntimeHealthResponse(
            status=bridge_snapshot.status,
            consecutive_failures=bridge_snapshot.consecutive_failures,
            last_error=bridge_snapshot.last_error,
            last_failure_at=bridge_snapshot.last_failure_at,
            last_success_at=bridge_snapshot.last_success_at,
            last_event_id=bridge_snapshot.last_event_id,
            poll_interval_seconds=settings.EVENT_BRIDGE_POLL_INTERVAL_SECONDS,
        ),
        event_stream=EventStreamRuntimeResponse(
            current_subscribers=current_subscribers,
            max_subscribers=settings.EVENT_STREAM_MAX_SUBSCRIBERS,
            subscriber_queue_size=settings.EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE,
            ping_interval_seconds=settings.EVENT_STREAM_PING_INTERVAL_SECONDS,
        ),
    )
