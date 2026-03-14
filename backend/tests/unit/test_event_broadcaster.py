from __future__ import annotations

import asyncio

from app.core.event_broadcaster import EventBroadcaster, TooManySubscribersError


def test_event_broadcaster_delivers_events_to_a_subscriber() -> None:
    async def exercise() -> None:
        broadcaster = EventBroadcaster()
        subscriber = broadcaster.subscribe()

        broadcaster.broadcast("system.event", {"id": 1, "message": "ready"})

        event = await asyncio.wait_for(subscriber.get(), timeout=1)
        assert event.event == "system.event"
        assert event.data == {"id": 1, "message": "ready"}

    asyncio.run(exercise())


def test_event_broadcaster_delivers_the_same_event_to_multiple_subscribers() -> None:
    async def exercise() -> None:
        broadcaster = EventBroadcaster()
        first = broadcaster.subscribe()
        second = broadcaster.subscribe()

        broadcaster.broadcast("agent.run_completed", {"id": 4, "agent_name": "firehose"})

        first_event = await asyncio.wait_for(first.get(), timeout=1)
        second_event = await asyncio.wait_for(second.get(), timeout=1)

        assert first_event == second_event
        assert broadcaster.subscriber_count() == 2

    asyncio.run(exercise())


def test_event_broadcaster_stops_sending_to_unsubscribed_queues() -> None:
    async def exercise() -> None:
        broadcaster = EventBroadcaster()
        subscriber = broadcaster.subscribe()
        broadcaster.unsubscribe(subscriber)

        broadcaster.broadcast("system.event", {"id": 9})

        assert broadcaster.subscriber_count() == 0
        try:
            await asyncio.wait_for(subscriber.get(), timeout=0.1)
        except TimeoutError:
            return
        raise AssertionError("unsubscribed queue unexpectedly received a broadcast")

    asyncio.run(exercise())


def test_event_broadcaster_rejects_subscribers_over_capacity() -> None:
    async def exercise() -> None:
        broadcaster = EventBroadcaster(max_subscribers=1)
        broadcaster.subscribe()

        try:
            broadcaster.subscribe()
        except TooManySubscribersError:
            return
        raise AssertionError("expected subscribe to reject connections above capacity")

    asyncio.run(exercise())


def test_event_broadcaster_drops_slow_subscribers_when_queue_is_full() -> None:
    async def exercise() -> None:
        broadcaster = EventBroadcaster(queue_maxsize=1)
        subscriber = broadcaster.subscribe()

        broadcaster.broadcast("system.event", {"id": 1})
        await asyncio.wait_for(asyncio.sleep(0), timeout=1)
        broadcaster.broadcast("system.event", {"id": 2})
        await asyncio.wait_for(asyncio.sleep(0), timeout=1)

        assert not broadcaster.has_subscriber(subscriber)
        assert broadcaster.subscriber_count() == 0

    asyncio.run(exercise())
