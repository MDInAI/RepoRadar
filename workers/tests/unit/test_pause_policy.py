"""Unit tests for pause policy evaluation."""
from agentic_workers.core.pause_policy import evaluate_pause_policy
from agentic_workers.storage.backend_models import FailureClassification, FailureSeverity


def test_github_rate_limit_pauses_firehose_and_backfill():
    """GitHub rate limit should pause both firehose and backfill."""
    decision = evaluate_pause_policy(
        agent_name="firehose",
        classification=FailureClassification.RATE_LIMITED,
        severity=FailureSeverity.ERROR,
        consecutive_failures=1,
    )
    assert decision.should_pause is True
    assert "firehose" in decision.affected_agents
    assert "backfill" in decision.affected_agents
    assert "bouncer" not in decision.affected_agents
    assert "analyst" not in decision.affected_agents


def test_github_rate_limit_from_backfill_pauses_both():
    """GitHub rate limit from backfill should also pause both agents."""
    decision = evaluate_pause_policy(
        agent_name="backfill",
        classification=FailureClassification.RATE_LIMITED,
        severity=FailureSeverity.ERROR,
        consecutive_failures=1,
    )
    assert decision.should_pause is True
    assert "firehose" in decision.affected_agents
    assert "backfill" in decision.affected_agents


def test_llm_rate_limit_pauses_analyst_only():
    """LLM rate limit should pause analyst only."""
    decision = evaluate_pause_policy(
        agent_name="analyst",
        classification=FailureClassification.RATE_LIMITED,
        severity=FailureSeverity.ERROR,
        consecutive_failures=1,
    )
    assert decision.should_pause is True
    assert decision.affected_agents == ["analyst"]
    assert "firehose" not in decision.affected_agents
    assert "backfill" not in decision.affected_agents


def test_blocking_failure_pauses_affected_agent_only():
    """Blocking failure should pause only the affected agent."""
    decision = evaluate_pause_policy(
        agent_name="bouncer",
        classification=FailureClassification.BLOCKING,
        severity=FailureSeverity.CRITICAL,
        consecutive_failures=1,
    )
    assert decision.should_pause is True
    assert decision.affected_agents == ["bouncer"]
    assert decision.resume_condition == "Operator review required"


def test_three_consecutive_retryable_failures_trigger_pause_for_non_intake_agents():
    """3+ consecutive retryable failures should still pause analyst-style agents."""
    decision = evaluate_pause_policy(
        agent_name="analyst",
        classification=FailureClassification.RETRYABLE,
        severity=FailureSeverity.ERROR,
        consecutive_failures=3,
    )
    assert decision.should_pause is True
    assert decision.affected_agents == ["analyst"]


def test_single_retryable_failure_does_not_pause():
    """Single retryable failure should not trigger pause."""
    decision = evaluate_pause_policy(
        agent_name="firehose",
        classification=FailureClassification.RETRYABLE,
        severity=FailureSeverity.WARNING,
        consecutive_failures=1,
    )
    assert decision.should_pause is False
    assert decision.affected_agents == []


def test_two_consecutive_retryable_failures_does_not_pause():
    """Two consecutive retryable failures should not trigger pause."""
    decision = evaluate_pause_policy(
        agent_name="backfill",
        classification=FailureClassification.RETRYABLE,
        severity=FailureSeverity.WARNING,
        consecutive_failures=2,
    )
    assert decision.should_pause is False


def test_three_consecutive_retryable_failures_do_not_pause_intake_agents():
    """Firehose/Backfill should keep auto-retrying transient intake failures."""
    decision = evaluate_pause_policy(
        agent_name="backfill",
        classification=FailureClassification.RETRYABLE,
        severity=FailureSeverity.ERROR,
        consecutive_failures=3,
    )
    assert decision.should_pause is False
    assert decision.affected_agents == []


def test_github_rate_limit_does_not_pause_analyst():
    """A GitHub rate limit seen by analyst should NOT pause analyst per AC2.

    GitHub rate limits pause firehose and backfill. The analyst fetches READMEs
    independently, but the story says GitHub limits must not pause analyst.
    """
    decision = evaluate_pause_policy(
        agent_name="analyst",
        classification=FailureClassification.RATE_LIMITED,
        severity=FailureSeverity.ERROR,
        consecutive_failures=1,
        upstream_provider="github",
    )
    assert decision.should_pause is False
    assert decision.affected_agents == []


def test_llm_rate_limit_with_explicit_provider_pauses_analyst():
    """An explicit LLM upstream provider rate limit should pause analyst."""
    decision = evaluate_pause_policy(
        agent_name="analyst",
        classification=FailureClassification.RATE_LIMITED,
        severity=FailureSeverity.ERROR,
        consecutive_failures=1,
        upstream_provider="llm",
    )
    assert decision.should_pause is True
    assert decision.affected_agents == ["analyst"]
    assert "firehose" not in decision.affected_agents
    assert "backfill" not in decision.affected_agents
