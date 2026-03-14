"""Pure pause policy evaluation for failure-triggered protective actions.

This module contains no side effects and no database access — it receives failure
context and returns a PauseDecision. Pause execution is the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass

from agentic_workers.storage.backend_models import FailureClassification, FailureSeverity


@dataclass
class PauseDecision:
    """Decision output from pause policy evaluation."""

    should_pause: bool
    reason: str
    affected_agents: list[str]
    resume_condition: str


def evaluate_pause_policy(
    agent_name: str,
    classification: FailureClassification,
    severity: FailureSeverity,
    consecutive_failures: int,
    upstream_provider: str | None = None,
) -> PauseDecision:
    """Evaluate whether a failure should trigger a pause.

    Pause rules (hardcoded in MVP):
    - GitHub rate limit: Pause firehose AND backfill (both use GitHub API)
    - LLM rate limit: Pause analyst only (GitHub rate limits do NOT pause analyst per AC2)
    - Blocking failure: Pause affected agent only
    - 3+ consecutive retryable failures: Pause affected agent
    - Single retryable failure: No pause
    """
    # GitHub rate limit affects all GitHub API consumers
    if classification == FailureClassification.RATE_LIMITED and agent_name in ("firehose", "backfill"):
        return PauseDecision(
            should_pause=True,
            reason="GitHub API rate limit exceeded",
            affected_agents=["firehose", "backfill"],
            resume_condition="Wait for rate-limit window to expire",
        )

    # LLM rate limit affects analyst only.
    # When upstream_provider="github", the analyst hit a GitHub rate limit while fetching READMEs.
    # Per AC2, GitHub rate limits pause firehose/backfill but NOT analyst.
    if (
        classification == FailureClassification.RATE_LIMITED
        and agent_name == "analyst"
        and upstream_provider != "github"
    ):
        return PauseDecision(
            should_pause=True,
            reason="LLM API rate limit exceeded",
            affected_agents=["analyst"],
            resume_condition="Wait for LLM rate-limit window to expire",
        )

    # Blocking failures pause the affected agent
    if classification == FailureClassification.BLOCKING:
        return PauseDecision(
            should_pause=True,
            reason=f"Blocking failure in {agent_name}",
            affected_agents=[agent_name],
            resume_condition="Operator review required",
        )

    # 3+ consecutive retryable failures trigger pause
    if classification == FailureClassification.RETRYABLE and consecutive_failures >= 3:
        return PauseDecision(
            should_pause=True,
            reason=f"{consecutive_failures} consecutive retryable failures in {agent_name}",
            affected_agents=[agent_name],
            resume_condition="Operator review or automatic retry after cooldown",
        )

    # Single retryable failure: no pause
    return PauseDecision(
        should_pause=False,
        reason="",
        affected_agents=[],
        resume_condition="",
    )
