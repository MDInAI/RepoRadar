from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import agentic_workers.jobs.bouncer_job as bouncer_job_module
from sqlmodel import Session, SQLModel, create_engine

from agentic_workers.jobs.bouncer_job import (
    BouncerRunResult,
    BouncerRunStatus,
    evaluate_repository,
    run_bouncer_job,
)
from agentic_workers.storage.backend_models import (
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
)


class EmptySession:
    def exec(self, _statement: object) -> "EmptySession":
        return self

    def all(self) -> list[object]:
        return []


class FailingRecoverySession:
    def __init__(self) -> None:
        now = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
        self.rows = [
            RepositoryIntake(
                github_repository_id=321,
                owner_login="octocat",
                repository_name="saas-platform",
                full_name="octocat/saas-platform",
                repository_description="Developer tools for SaaS teams",
                queue_status=RepositoryQueueStatus.PENDING,
                triage_status=RepositoryTriageStatus.PENDING,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            )
        ]

    def exec(self, _statement: object) -> "FailingRecoverySession":
        return self

    def all(self) -> list[RepositoryIntake]:
        return self.rows

    def add(self, _row: object) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def get(self, _model: object, _key: object) -> RepositoryIntake | None:
        raise RuntimeError("database connection lost during failure recovery")


def _make_session(tmp_path: Path) -> Session:
    database_url = f"sqlite:///{tmp_path / 'bouncer-unit.db'}"
    engine = create_engine(database_url)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _pending_row(repository_id: int, full_name: str) -> RepositoryIntake:
    owner_login, repository_name = full_name.split("/", maxsplit=1)
    now = datetime(2026, 3, 8, 12, repository_id % 60, tzinfo=timezone.utc)
    return RepositoryIntake(
        github_repository_id=repository_id,
        owner_login=owner_login,
        repository_name=repository_name,
        full_name=full_name,
        repository_description="Developer tools for SaaS teams",
        queue_status=RepositoryQueueStatus.PENDING,
        triage_status=RepositoryTriageStatus.PENDING,
        discovered_at=now,
        queue_created_at=now,
        status_updated_at=now,
    )


def test_bouncer_evaluator_rejects_repository_when_exclude_rule_matches() -> None:
    decision = evaluate_repository(
        full_name="octocat/tutorial-platform",
        description="A tutorial repo for learning",
        include_rules=("saas",),
        exclude_rules=("tutorial",),
    )

    assert decision.triage_status is RepositoryTriageStatus.REJECTED
    assert decision.explanation_kind is RepositoryTriageExplanationKind.EXCLUDE_RULE
    assert decision.explanation_summary == "Rejected because exclude rules matched: tutorial."
    assert decision.matched_exclude_rules == ("tutorial",)


def test_bouncer_evaluator_requires_include_match_when_allowlist_is_configured() -> None:
    decision = evaluate_repository(
        full_name="octocat/random-repo",
        description="Infrastructure automation for platform teams",
        include_rules=("saas", "developer tools"),
        exclude_rules=(),
    )

    assert decision.triage_status is RepositoryTriageStatus.REJECTED
    assert decision.explanation_kind is RepositoryTriageExplanationKind.ALLOWLIST_MISS
    assert (
        decision.explanation_summary
        == "Rejected because no include rules matched the configured allowlist."
    )
    assert decision.matched_include_rules == ()


def test_bouncer_evaluator_uses_word_boundaries_for_matching() -> None:
    decision = evaluate_repository(
        full_name="octocat/isaas-platform",
        description="Infrastructure automation for platform teams",
        include_rules=("saas",),
        exclude_rules=(),
    )

    # "saas" should not match "isaas"
    assert decision.triage_status is RepositoryTriageStatus.REJECTED
    assert decision.explanation_kind is RepositoryTriageExplanationKind.ALLOWLIST_MISS
    assert decision.matched_include_rules == ()


def test_bouncer_evaluator_accepts_repository_when_include_rule_matches() -> None:
    decision = evaluate_repository(
        full_name="octocat/saas-platform",
        description="Developer tools for SaaS operators",
        include_rules=("saas",),
        exclude_rules=(),
    )

    assert decision.triage_status is RepositoryTriageStatus.ACCEPTED
    assert decision.explanation_kind is RepositoryTriageExplanationKind.INCLUDE_RULE
    assert decision.explanation_summary == "Accepted because include rules matched: saas."
    assert decision.matched_include_rules == ("saas",)


def test_bouncer_evaluator_accepts_repository_when_not_excluded_and_no_allowlist_exists() -> None:
    decision = evaluate_repository(
        full_name="octocat/infra-platform",
        description="Infrastructure automation for platform teams",
        include_rules=(),
        exclude_rules=("gaming",),
    )

    assert decision.triage_status is RepositoryTriageStatus.ACCEPTED
    assert decision.explanation_kind is RepositoryTriageExplanationKind.PASS_THROUGH
    assert (
        decision.explanation_summary
        == "Accepted because no include allowlist is configured and no exclude rules matched."
    )


def test_bouncer_job_returns_success_with_empty_queue_and_artifact_failure(tmp_path: Path) -> None:
    def failing_artifact_writer(**_kwargs: object) -> Path | None:
        raise OSError("runtime directory is read-only")

    result = run_bouncer_job(
        session=EmptySession(),  # type: ignore[arg-type]
        runtime_dir=tmp_path,
        include_rules=("saas",),
        exclude_rules=("gaming",),
        write_artifact=failing_artifact_writer,
    )

    assert isinstance(result, BouncerRunResult)
    assert result.status is BouncerRunStatus.PARTIAL_FAILURE
    assert result.outcomes == []
    assert result.artifact_path is None
    assert result.artifact_error == "runtime directory is read-only"


def test_bouncer_job_reports_failure_when_recovery_write_also_fails(tmp_path: Path, monkeypatch) -> None:
    def fail_explanation_persist(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("explanation write failed")

    monkeypatch.setattr(
        "agentic_workers.jobs.bouncer_job._upsert_triage_explanation",
        fail_explanation_persist,
    )

    result = run_bouncer_job(
        session=FailingRecoverySession(),  # type: ignore[arg-type]
        runtime_dir=tmp_path,
        include_rules=("saas",),
        exclude_rules=(),
    )

    assert result.status is BouncerRunStatus.FAILED
    assert len(result.outcomes) == 1
    assert result.outcomes[0].queue_status is RepositoryQueueStatus.FAILED
    assert result.outcomes[0].error == (
        "explanation write failed | "
        "failure status update skipped: database connection lost during failure recovery"
    )


def test_bouncer_persists_failure_state_when_event_emission_rolls_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with _make_session(tmp_path) as session:
        session.add(_pending_row(654, "octocat/event-sink-failure"))
        session.commit()

        monkeypatch.setattr(
            "agentic_workers.jobs.bouncer_job._upsert_triage_explanation",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("explanation write failed")),
        )
        monkeypatch.setattr(
            "agentic_workers.jobs.bouncer_job.emit_failure_event",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("event sink failed")),
        )

        result = run_bouncer_job(
            session=session,
            runtime_dir=tmp_path,
            include_rules=("saas",),
            exclude_rules=(),
        )
        row = session.get(RepositoryIntake, 654)

    assert result.status is BouncerRunStatus.FAILED
    assert row is not None
    assert row.queue_status is RepositoryQueueStatus.FAILED


def test_bouncer_job_returns_skipped_paused_when_agent_is_paused(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(bouncer_job_module, "is_agent_paused", lambda *_args, **_kwargs: True)

    class UnexpectedQueueSession(EmptySession):
        def all(self) -> list[object]:
            raise AssertionError("queue lookup should not run while paused")

    result = run_bouncer_job(
        session=UnexpectedQueueSession(),  # type: ignore[arg-type]
        runtime_dir=tmp_path,
    )

    assert result.status is BouncerRunStatus.SKIPPED_PAUSED
    assert result.outcomes == []
