from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class EventBridgeHealthSnapshot:
    consecutive_failures: int
    last_error: str | None
    last_failure_at: datetime | None
    last_success_at: datetime | None
    last_event_id: int | None

    @property
    def status(self) -> str:
        return "degraded" if self.consecutive_failures > 0 else "healthy"


@dataclass(slots=True)
class EventBridgeHealth:
    consecutive_failures: int = 0
    last_error: str | None = None
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
    last_event_id: int | None = None
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def record_success(self, last_event_id: int | None) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.last_error = None
            self.last_success_at = _utcnow()
            self.last_event_id = last_event_id

    def record_failure(self, error: Exception) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.last_error = str(error)
            self.last_failure_at = _utcnow()

    def snapshot(self) -> EventBridgeHealthSnapshot:
        with self._lock:
            return EventBridgeHealthSnapshot(
                consecutive_failures=self.consecutive_failures,
                last_error=self.last_error,
                last_failure_at=self.last_failure_at,
                last_success_at=self.last_success_at,
                last_event_id=self.last_event_id,
            )

