from __future__ import annotations

import asyncio
import ast
import json

import pytest

from app.api.routes import events_stream
from app.core.config import settings
from app.core.errors import AppError
from app.api.routes.events_stream import stream_events
from app.core.event_broadcaster import EventBroadcaster


class StubRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


@pytest.mark.asyncio
async def test_events_stream_route_returns_event_stream_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_ping = settings.EVENT_STREAM_PING_INTERVAL_SECONDS
    settings.EVENT_STREAM_PING_INTERVAL_SECONDS = 9.0
    broadcaster = EventBroadcaster()
    request = StubRequest()
    captured_ping: dict[str, float] = {}

    class ObservedEventSourceResponse:
        def __init__(self, content: object, *, ping: float) -> None:
            captured_ping["value"] = ping
            self.body_iterator = content
            self.media_type = "text/event-stream"

    monkeypatch.setattr(events_stream, "EventSourceResponse", ObservedEventSourceResponse)

    try:
        response = await stream_events(request=request, broadcaster=broadcaster)
        iterator = response.body_iterator.__aiter__()

        assert response.media_type == "text/event-stream"
        assert captured_ping["value"] == 9.0
        assert broadcaster.subscriber_count() == 1

        broadcaster.broadcast(
            "system.event",
            {"id": 7, "event_type": "agent_started", "agent_name": "firehose"},
        )

        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=1)
        text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
        payload = ast.literal_eval(text)

        assert payload["event"] == "system.event"
        assert json.loads(payload["data"]) == {
            "agent_name": "firehose",
            "event_type": "agent_started",
            "id": 7,
        }

        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(iterator.__anext__(), timeout=2)
        assert broadcaster.subscriber_count() == 0
    finally:
        settings.EVENT_STREAM_PING_INTERVAL_SECONDS = original_ping


@pytest.mark.asyncio
async def test_events_stream_route_unsubscribes_after_client_disconnect() -> None:
    broadcaster = EventBroadcaster()
    request = StubRequest()

    response = await stream_events(request=request, broadcaster=broadcaster)
    iterator = response.body_iterator.__aiter__()
    assert broadcaster.subscriber_count() == 1

    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(iterator.__anext__(), timeout=2)

    assert broadcaster.subscriber_count() == 0


@pytest.mark.asyncio
async def test_events_stream_route_returns_503_when_subscriber_capacity_is_reached() -> None:
    broadcaster = EventBroadcaster(max_subscribers=1)
    request = StubRequest()

    first_response = await stream_events(request=request, broadcaster=broadcaster)
    iterator = first_response.body_iterator.__aiter__()
    assert broadcaster.subscriber_count() == 1

    with pytest.raises(AppError) as exc_info:
        await stream_events(request=StubRequest(), broadcaster=broadcaster)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "event_stream_at_capacity"

    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(iterator.__anext__(), timeout=2)
