from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.api.deps import get_backfill_timeline_service
from app.main import app


class _FakeBackfillTimelineService:
    def get_timeline(self):
        return {
            "agent_name": "backfill",
            "oldest_date_in_window": date(2025, 9, 15),
            "newest_boundary_exclusive": date(2025, 10, 15),
            "current_cursor": None,
            "next_page": 1,
            "exhausted": False,
            "resume_required": True,
            "last_checkpointed_at": None,
            "summary": "Backfill scans inside this historical window.",
            "notes": ["Cursor resets when you save."],
        }

    def update_timeline(self, request):
        payload = self.get_timeline()
        payload["oldest_date_in_window"] = request.oldest_date_in_window
        payload["newest_boundary_exclusive"] = request.newest_boundary_exclusive
        payload["message"] = "Saved Backfill timeline"
        return payload


def test_get_backfill_timeline_route_returns_checkpoint() -> None:
    with TestClient(app) as test_client:
        app.dependency_overrides[get_backfill_timeline_service] = lambda: _FakeBackfillTimelineService()
        try:
            response = test_client.get("/api/v1/agents/backfill/timeline")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["oldest_date_in_window"] == "2025-09-15"
    assert data["newest_boundary_exclusive"] == "2025-10-15"


def test_patch_backfill_timeline_route_returns_saved_window() -> None:
    with TestClient(app) as test_client:
        app.dependency_overrides[get_backfill_timeline_service] = lambda: _FakeBackfillTimelineService()
        try:
            response = test_client.patch(
                "/api/v1/agents/backfill/timeline",
                json={
                    "oldest_date_in_window": "2025-08-01",
                    "newest_boundary_exclusive": "2025-09-01",
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Saved Backfill timeline"
    assert data["oldest_date_in_window"] == "2025-08-01"
