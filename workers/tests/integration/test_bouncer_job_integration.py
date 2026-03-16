from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.jobs import bouncer_job
from agentic_workers.jobs.bouncer_job import BouncerRunStatus, run_bouncer_job
from agentic_workers.storage.backend_models import (
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
    SQLModel,
)


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'bouncer.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _pending_row(
    repository_id: int,
    *,
    full_name: str,
    description: str | None,
) -> RepositoryIntake:
    now = datetime(2026, 3, 8, 12, repository_id % 60, tzinfo=timezone.utc)
    owner_login, repository_name = full_name.split("/", maxsplit=1)
    return RepositoryIntake(
        github_repository_id=repository_id,
        owner_login=owner_login,
        repository_name=repository_name,
        full_name=full_name,
        repository_description=description,
        queue_status=RepositoryQueueStatus.PENDING,
        triage_status=RepositoryTriageStatus.PENDING,
        discovered_at=now,
        queue_created_at=now,
        status_updated_at=now,
    )


def test_bouncer_job_persists_triage_outcomes_and_runtime_artifact(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    with _make_session(tmp_path) as session:
        session.add(
            _pending_row(
                101,
                full_name="octocat/saas-platform",
                description="Developer tools for SaaS infrastructure teams",
            )
        )
        session.add(
            _pending_row(
                202,
                full_name="octocat/tutorial-starter",
                description="Gaming tutorial starter kit",
            )
        )
        session.commit()

        result = run_bouncer_job(
            session=session,
            runtime_dir=runtime_dir,
            include_rules=("saas", "developer tools"),
            exclude_rules=("gaming", "tutorial"),
        )
        rows = session.exec(
            select(RepositoryIntake).order_by(RepositoryIntake.github_repository_id)
        ).all()
        explanations = session.exec(
            select(RepositoryTriageExplanation).order_by(
                RepositoryTriageExplanation.github_repository_id
            )
        ).all()

    assert result.status is BouncerRunStatus.SUCCESS
    outcomes_by_repository_id = {
        outcome.github_repository_id: outcome
        for outcome in result.outcomes
    }
    assert outcomes_by_repository_id[101].triage_status is RepositoryTriageStatus.ACCEPTED
    assert outcomes_by_repository_id[202].triage_status is RepositoryTriageStatus.REJECTED
    assert rows[0].queue_status is RepositoryQueueStatus.COMPLETED
    assert rows[0].triage_status is RepositoryTriageStatus.ACCEPTED
    assert rows[0].triaged_at is not None
    assert rows[0].processing_completed_at is not None
    assert rows[1].queue_status is RepositoryQueueStatus.COMPLETED
    assert rows[1].triage_status is RepositoryTriageStatus.REJECTED
    assert rows[1].triaged_at is not None
    assert explanations[0].github_repository_id == 101
    assert explanations[0].explanation_kind is RepositoryTriageExplanationKind.INCLUDE_RULE
    assert explanations[0].explanation_summary == (
        "Accepted because include rules matched: saas, developer tools."
    )
    assert explanations[0].matched_include_rules == ["saas", "developer tools"]
    assert explanations[0].matched_exclude_rules == []
    assert explanations[0].triage_logic_version == bouncer_job.TRIAGE_LOGIC_VERSION
    assert explanations[0].triage_config_fingerprint is not None
    assert explanations[1].github_repository_id == 202
    assert explanations[1].explanation_kind is RepositoryTriageExplanationKind.EXCLUDE_RULE
    assert explanations[1].explanation_summary == (
        "Rejected because exclude rules matched: gaming, tutorial."
    )
    assert explanations[1].matched_include_rules == []
    assert explanations[1].matched_exclude_rules == ["gaming", "tutorial"]
    assert explanations[1].triage_logic_version == bouncer_job.TRIAGE_LOGIC_VERSION
    assert explanations[1].triage_config_fingerprint is not None

    artifact = json.loads(result.artifact_path.read_text())  # type: ignore[union-attr]
    assert artifact["status"] == "success"
    assert artifact["summary"] == {"accepted": 1, "failed": 0, "rejected": 1}
    artifact_outcomes = {
        item["github_repository_id"]: item
        for item in artifact["outcomes"]
    }
    assert artifact_outcomes[101]["explanation_kind"] == "include_rule"
    assert artifact_outcomes[101]["explanation_summary"] == (
        "Accepted because include rules matched: saas, developer tools."
    )
    assert artifact_outcomes[101]["matched_include_rules"] == ["saas", "developer tools"]
    assert artifact_outcomes[202]["explanation_kind"] == "exclude_rule"
    assert artifact_outcomes[202]["explanation_summary"] == (
        "Rejected because exclude rules matched: gaming, tutorial."
    )
    assert artifact_outcomes[202]["matched_exclude_rules"] == ["gaming", "tutorial"]


def test_bouncer_job_rolls_back_triage_snapshot_when_explanation_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    with _make_session(tmp_path) as session:
        session.add(
            _pending_row(
                303,
                full_name="octocat/saas-platform",
                description="Developer tools for SaaS infrastructure teams",
            )
        )
        session.commit()

        def fail_explanation_persist(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("explanation write failed")

        monkeypatch.setattr(bouncer_job, "_upsert_triage_explanation", fail_explanation_persist)

        result = bouncer_job.run_bouncer_job(
            session=session,
            runtime_dir=runtime_dir,
            include_rules=("saas",),
            exclude_rules=(),
        )
        row = session.get(RepositoryIntake, 303)
        explanation = session.get(RepositoryTriageExplanation, 303)

    assert result.status is BouncerRunStatus.FAILED
    assert len(result.outcomes) == 1
    assert result.outcomes[0].queue_status is RepositoryQueueStatus.FAILED
    assert result.outcomes[0].triage_status is None
    assert result.outcomes[0].error == "explanation write failed"
    assert row is not None
    assert row.queue_status is RepositoryQueueStatus.FAILED
    assert row.triage_status is RepositoryTriageStatus.PENDING
    assert row.triaged_at is None
    assert row.processing_completed_at is None
    assert explanation is None
