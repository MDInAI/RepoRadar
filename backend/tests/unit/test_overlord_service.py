from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlmodel import Session, select

from app.models import AgentPauseState, EventSeverity, RepositoryAnalysisStatus, RepositoryIntake, RepositoryQueueStatus, RepositoryTriageStatus
from app.schemas.gateway_contract import GeminiApiKeyPoolSnapshot, GeminiApiKeySnapshot, GitHubApiBudgetSnapshot
from app.services.overlord_service import OverlordService, OverlordSettings


class FakeGatewayContractService:
    def __init__(self, *, github_budget=None, gemini_pool=None) -> None:
        self.github_budget = github_budget
        self.gemini_pool = gemini_pool

    def get_runtime_surface(self):
        return SimpleNamespace(
            runtime=SimpleNamespace(
                github_api_budget=self.github_budget,
                gemini_api_key_pool=self.gemini_pool,
            )
        )


def test_overlord_summary_surfaces_rate_limit_and_blocked_backlog(session: Session) -> None:
    now = datetime.now(timezone.utc)
    for repo_id in range(1, 31):
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
            pause_reason="Manual pause for maintenance",
        )
    )
    session.commit()

    github_budget = GitHubApiBudgetSnapshot(
        captured_at=now,
        exhausted=True,
        retry_after_seconds=900,
        remaining=0,
        limit=5000,
    )

    service = OverlordService(
        session=session,
        gateway_contract_service=FakeGatewayContractService(github_budget=github_budget),
        settings=OverlordSettings(),
    )

    summary = service.get_summary()

    assert summary.status == "blocked"
    assert summary.incidents[0].incident_key == "analyst-blocked-backlog"
    assert any(incident.incident_key == "github-budget-exhausted" for incident in summary.incidents)
    assert any("Review why Analyst is paused" in todo for todo in summary.operator_todos)
    assert summary.telemetry["analysis_pending"] == 30
    assert summary.telemetry["github_budget_exhausted"] is True


def test_overlord_evaluate_and_remediate_safe_pauses_and_resumes_agents(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("ANALYST_PROVIDER", "gemini")
    now = datetime.now(timezone.utc)
    github_budget = GitHubApiBudgetSnapshot(
        captured_at=now,
        exhausted=True,
        retry_after_seconds=600,
        remaining=0,
        limit=5000,
    )
    gemini_pool = GeminiApiKeyPoolSnapshot(
        captured_at=now,
        keys=[
            GeminiApiKeySnapshot(
                label="key-1",
                status="daily-limit",
                cooldown_until=now + timedelta(hours=8),
            )
        ],
    )

    service = OverlordService(
        session=session,
        gateway_contract_service=FakeGatewayContractService(
            github_budget=github_budget,
            gemini_pool=gemini_pool,
        ),
        settings=OverlordSettings(),
    )

    service.evaluate_and_remediate()

    pause_states = {
        state.agent_name: state
        for state in session.exec(select(AgentPauseState)).all()
    }
    assert pause_states["firehose"].is_paused is True
    assert pause_states["backfill"].is_paused is True
    assert pause_states["analyst"].is_paused is True
    assert "Overlord safe-paused intake" in (pause_states["firehose"].pause_reason or "")
    assert "Overlord safe-paused Analyst" in (pause_states["analyst"].pause_reason or "")

    recovered_service = OverlordService(
        session=session,
        gateway_contract_service=FakeGatewayContractService(
            github_budget=GitHubApiBudgetSnapshot(
                captured_at=now + timedelta(minutes=15),
                exhausted=False,
                remaining=4200,
                limit=5000,
            ),
            gemini_pool=GeminiApiKeyPoolSnapshot(
                captured_at=now + timedelta(minutes=15),
                keys=[GeminiApiKeySnapshot(label="key-1", status="available")],
            ),
        ),
        settings=OverlordSettings(),
    )

    recovered_service.evaluate_and_remediate()
    session.expire_all()

    pause_states = {
        state.agent_name: state
        for state in session.exec(select(AgentPauseState)).all()
    }
    assert pause_states["firehose"].is_paused is False
    assert pause_states["backfill"].is_paused is False
    assert pause_states["analyst"].is_paused is False
