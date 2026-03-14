"""Pure failure classification service for upstream provider errors.

These functions have no side effects and no database access — they receive an
exception and return a classification + severity.  Event emission is the
caller's responsibility (see events.emit_failure_event).
"""
from __future__ import annotations

from agentic_workers.storage.backend_models import FailureClassification, FailureSeverity
from agentic_workers.providers.github_provider import (
    GitHubPayloadError,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
)


def classify_github_error(error: GitHubProviderError) -> FailureClassification:
    """Map a GitHub provider exception to a FailureClassification.

    - GitHubRateLimitError       → rate_limited
    - GitHubReadmeNotFoundError  → blocking  (404, no point retrying same repo)
    - GitHubPayloadError         → blocking  (malformed response, not transient)
    - GitHubProviderError        → retryable (generic transport / HTTP failure)
    """
    if isinstance(error, GitHubRateLimitError):
        return FailureClassification.RATE_LIMITED
    if isinstance(error, (GitHubReadmeNotFoundError, GitHubPayloadError)):
        return FailureClassification.BLOCKING
    # Base GitHubProviderError covers URLError and generic HTTP failures
    return FailureClassification.RETRYABLE


def classify_llm_error(error: Exception) -> FailureClassification:
    """Map an LLM provider exception to a FailureClassification.

    Inspects the exception message and type name to infer classification so
    that this function works with any LLM SDK without requiring imports.

    - Timeout / connection errors → retryable
    - HTTP 429 / rate-limit       → rate_limited
    - Auth / 401 / 403            → blocking
    - All others                  → retryable (assume transient by default)
    """
    error_type = type(error).__name__.lower()
    error_message = str(error).lower()

    # Auth failures are blocking — no amount of retrying will help
    if any(kw in error_type for kw in ("auth", "unauthorized", "forbidden", "permission")):
        return FailureClassification.BLOCKING
    if any(kw in error_message for kw in ("401", "403", "unauthorized", "forbidden", "authentication")):
        return FailureClassification.BLOCKING

    # Rate-limit signals
    if "ratelimit" in error_type or "rate_limit" in error_type:
        return FailureClassification.RATE_LIMITED
    if any(kw in error_message for kw in ("429", "rate limit", "rate_limit", "too many requests")):
        return FailureClassification.RATE_LIMITED

    # Default: assume transient (timeout, network, temporary server error)
    return FailureClassification.RETRYABLE


def determine_severity(
    classification: FailureClassification,
    consecutive_failures: int,
) -> FailureSeverity:
    """Derive FailureSeverity from classification and how many failures in a row.

    Rules:
    - blocking                    → critical  (always)
    - rate_limited                → error     (always — indicates quota exhaustion)
    - retryable, 1-2 occurrences  → warning   (occasional, likely transient)
    - retryable, 3+  occurrences  → error     (persistent, needs attention)
    """
    if classification is FailureClassification.BLOCKING:
        return FailureSeverity.CRITICAL
    if classification is FailureClassification.RATE_LIMITED:
        return FailureSeverity.ERROR
    # retryable
    if consecutive_failures >= 3:
        return FailureSeverity.ERROR
    return FailureSeverity.WARNING
