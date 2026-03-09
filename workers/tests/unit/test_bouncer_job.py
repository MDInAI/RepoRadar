from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

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
