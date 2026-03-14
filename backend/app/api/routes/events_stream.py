from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from app.api.deps import get_event_broadcaster
from app.core.config import settings
from app.core.errors import AppError
from app.core.event_broadcaster import EventBroadcaster
from app.core.event_broadcaster import TooManySubscribersError


router = APIRouter()


@router.get("/events/stream")
async def stream_events(
    request: Request,
    broadcaster: EventBroadcaster = Depends(get_event_broadcaster),
) -> EventSourceResponse:
    try:
        queue = broadcaster.subscribe()
    except TooManySubscribersError as exc:
        raise AppError(
            message="The event stream is temporarily at capacity. Please retry shortly.",
            code="event_stream_at_capacity",
            status_code=503,
            details={"max_subscribers": settings.EVENT_STREAM_MAX_SUBSCRIBERS},
        ) from exc

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if not broadcaster.has_subscriber(queue):
                        break
                    continue
                yield {
                    "event": message.event,
                    "data": json.dumps(message.data, sort_keys=True),
                }
        finally:
            broadcaster.unsubscribe(queue)

    return EventSourceResponse(
        event_generator(),
        ping=settings.EVENT_STREAM_PING_INTERVAL_SECONDS,
    )
