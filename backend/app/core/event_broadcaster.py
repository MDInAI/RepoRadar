from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class BroadcastEvent:
    event: str
    data: dict[str, object]


@dataclass(slots=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[BroadcastEvent]


class TooManySubscribersError(RuntimeError):
    pass


class EventBroadcaster:
    def __init__(
        self,
        *,
        max_subscribers: int | None = None,
        queue_maxsize: int = 100,
    ) -> None:
        self._subscribers: dict[int, _Subscriber] = {}
        self._max_subscribers = max_subscribers
        self._queue_maxsize = queue_maxsize
        self._lock = Lock()

    def subscribe(self) -> asyncio.Queue[BroadcastEvent]:
        with self._lock:
            if (
                self._max_subscribers is not None
                and len(self._subscribers) >= self._max_subscribers
            ):
                raise TooManySubscribersError("Event stream subscriber limit reached.")

            queue: asyncio.Queue[BroadcastEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
            self._subscribers[id(queue)] = _Subscriber(
                loop=asyncio.get_running_loop(),
                queue=queue,
            )
        return queue

    def unsubscribe(self, queue: asyncio.Queue[BroadcastEvent]) -> None:
        with self._lock:
            self._subscribers.pop(id(queue), None)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def has_subscriber(self, queue: asyncio.Queue[BroadcastEvent]) -> bool:
        with self._lock:
            return id(queue) in self._subscribers

    def broadcast(self, event_type: str, data: dict[str, object]) -> None:
        message = BroadcastEvent(event=event_type, data=data)
        with self._lock:
            subscribers = list(self._subscribers.items())

        for subscriber_id, subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(
                    self._enqueue_message,
                    subscriber_id,
                    message,
                )
            except RuntimeError:
                self._drop_subscriber(subscriber_id)

    def _enqueue_message(self, subscriber_id: int, message: BroadcastEvent) -> None:
        with self._lock:
            subscriber = self._subscribers.get(subscriber_id)
        if subscriber is None:
            return

        try:
            subscriber.queue.put_nowait(message)
        except asyncio.QueueFull:
            self._drop_subscriber(subscriber_id)

    def _drop_subscriber(self, subscriber_id: int) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)
