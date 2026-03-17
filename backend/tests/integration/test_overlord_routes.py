from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db_session
from app.core.config import settings
from app.main import app
from app.models import AgentPauseState, RepositoryAnalysisStatus, RepositoryIntake, RepositoryQueueStatus, RepositoryTriageStatus


@pytest.fixture
def session(tmp_path: Path, monkeypatch) -> Iterator[Session]:
    monkeypatch.setenv("ANALYST_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AGENTIC_RUNTIME_DIR", tmp_path)
    (tmp_path / "github").mkdir()
    (tmp_path / "gemini").mkdir()
    (tmp_path / "github" / "quota.json").write_text(
        """
        {
          "provider": "github",
          "captured_at": "2026-03-17T01:00:00+00:00",
          "remaining": 0,
          "limit": 5000,
          "retry_after_seconds": 900,
          "exhausted": true
        }
        """.strip(),
        encoding="utf-8",
    )
    (tmp_path / "gemini" / "key_pool.json").write_text(
        """
        {
          "provider": "gemini-compatible",
          "captured_at": "2026-03-17T01:00:00+00:00",
          "keys": [
            {
              "label": "key-1",
              "status": "daily-limit",
              "cooldown_until": "2026-03-18T01:00:00+00:00"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db_session = Session(engine)
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def override_get_db_session():
        yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_overlord_summary_returns_plain_language_incidents(client: TestClient, session: Session) -> None:
    now = datetime.now(timezone.utc)
    for repo_id in range(1, 28):
        session.add(
            RepositoryIntake(
                github_repository_id=repo_id,
                owner_login="octocat",
                repository_name=f"repo-{repo_id}",
                full_name=f"octocat/repo-{repo_id}",
                queue_status=RepositoryQueueStatus.COMPLETED,
                triage_status=RepositoryTriageStatus.ACCEPTED,
                analysis_status=RepositoryAnalysisStatus.PENDING,
            )
        )
    session.add(
        AgentPauseState(
            agent_name="analyst",
            is_paused=True,
            paused_at=now,
            pause_reason="Manual pause while provider is unstable",
        )
    )
    session.commit()

    response = client.get("/api/v1/overlord/summary")
    assert response.status_code == 200
    payload = response.json()

    assert payload["agent_name"] == "overlord"
    assert payload["display_name"] == "Overlord"
    assert payload["status"] == "blocked"
    assert payload["incidents"]
    assert payload["incidents"][0]["incident_key"] == "analyst-blocked-backlog"
    assert any(incident["incident_key"] == "github-budget-exhausted" for incident in payload["incidents"])
    assert any(incident["incident_key"] == "gemini-pool-exhausted" for incident in payload["incidents"])
    assert payload["telegram"]["enabled"] is False


def test_get_overlord_policy_returns_current_policy_flags(client: TestClient) -> None:
    response = client.get("/api/v1/overlord/policy")
    assert response.status_code == 200
    payload = response.json()

    assert payload == {
        "auto_remediation_enabled": True,
        "safe_pause_enabled": True,
        "safe_resume_enabled": True,
        "stale_state_cleanup_enabled": True,
        "telegram": {
            "enabled": False,
            "min_severity": "error",
            "daily_digest_enabled": False,
            "configured_chat": False,
            "configured_token": False,
        },
    }
