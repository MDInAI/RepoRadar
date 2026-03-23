from __future__ import annotations

import pytest

from agentic_workers.core.failure_detector import (
    classify_github_error,
    classify_github_runtime_error,
    classify_llm_error,
    determine_severity,
)
from agentic_workers.providers.github_provider import (
    GitHubPayloadError,
    GitHubProviderError,
    GitHubRateLimitError,
    GitHubReadmeNotFoundError,
)
from agentic_workers.storage.backend_models import FailureClassification, FailureSeverity


class TestClassifyGitHubError:
    def test_rate_limit_error_maps_to_rate_limited(self) -> None:
        exc = GitHubRateLimitError(status_code=429, retry_after_seconds=60)
        assert classify_github_error(exc) is FailureClassification.RATE_LIMITED

    def test_rate_limit_without_retry_after_maps_to_rate_limited(self) -> None:
        exc = GitHubRateLimitError(status_code=403, retry_after_seconds=None)
        assert classify_github_error(exc) is FailureClassification.RATE_LIMITED

    def test_readme_not_found_maps_to_blocking(self) -> None:
        exc = GitHubReadmeNotFoundError("README not found")
        assert classify_github_error(exc) is FailureClassification.BLOCKING

    def test_payload_error_maps_to_blocking(self) -> None:
        exc = GitHubPayloadError("malformed JSON")
        assert classify_github_error(exc) is FailureClassification.BLOCKING

    def test_generic_provider_error_maps_to_retryable(self) -> None:
        exc = GitHubProviderError("connection reset")
        assert classify_github_error(exc) is FailureClassification.RETRYABLE

    def test_rate_limit_takes_precedence_over_base_class(self) -> None:
        # GitHubRateLimitError IS-A GitHubProviderError — subclass check must fire first
        exc = GitHubRateLimitError(status_code=429, retry_after_seconds=30)
        result = classify_github_error(exc)
        assert result is FailureClassification.RATE_LIMITED
        assert result is not FailureClassification.RETRYABLE


class TestClassifyGitHubRuntimeError:
    def test_timeout_error_maps_to_retryable(self) -> None:
        exc = TimeoutError("The read operation timed out")
        assert classify_github_runtime_error(exc) is FailureClassification.RETRYABLE

    def test_connection_error_maps_to_retryable(self) -> None:
        exc = ConnectionError("connection reset by peer")
        assert classify_github_runtime_error(exc) is FailureClassification.RETRYABLE

    def test_rate_limit_message_maps_to_rate_limited(self) -> None:
        exc = RuntimeError("HTTP 429: Too Many Requests")
        assert classify_github_runtime_error(exc) is FailureClassification.RATE_LIMITED

    def test_generic_runtime_error_defaults_to_blocking(self) -> None:
        exc = RuntimeError("unexpected backfill crash")
        assert classify_github_runtime_error(exc) is FailureClassification.BLOCKING


class TestClassifyLlmError:
    def test_auth_in_type_name_maps_to_blocking(self) -> None:
        class AuthenticationError(Exception):
            pass

        exc = AuthenticationError("invalid api key")
        assert classify_llm_error(exc) is FailureClassification.BLOCKING

    def test_401_in_message_maps_to_blocking(self) -> None:
        exc = ValueError("HTTP 401: Unauthorized")
        assert classify_llm_error(exc) is FailureClassification.BLOCKING

    def test_403_in_message_maps_to_blocking(self) -> None:
        exc = ValueError("403 Forbidden: access denied")
        assert classify_llm_error(exc) is FailureClassification.BLOCKING

    def test_unauthorized_in_message_maps_to_blocking(self) -> None:
        exc = RuntimeError("unauthorized request to API")
        assert classify_llm_error(exc) is FailureClassification.BLOCKING

    def test_rate_limit_in_type_name_maps_to_rate_limited(self) -> None:
        class RateLimitError(Exception):
            pass

        exc = RateLimitError("quota exceeded")
        assert classify_llm_error(exc) is FailureClassification.RATE_LIMITED

    def test_429_in_message_maps_to_rate_limited(self) -> None:
        exc = ValueError("HTTP 429: Too Many Requests")
        assert classify_llm_error(exc) is FailureClassification.RATE_LIMITED

    def test_rate_limit_phrase_in_message(self) -> None:
        exc = RuntimeError("rate limit exceeded for model claude-sonnet")
        assert classify_llm_error(exc) is FailureClassification.RATE_LIMITED

    def test_too_many_requests_in_message(self) -> None:
        exc = RuntimeError("too many requests, slow down")
        assert classify_llm_error(exc) is FailureClassification.RATE_LIMITED

    def test_timeout_error_maps_to_retryable(self) -> None:
        exc = TimeoutError("request timed out after 30s")
        assert classify_llm_error(exc) is FailureClassification.RETRYABLE

    def test_connection_error_maps_to_retryable(self) -> None:
        exc = ConnectionError("failed to connect to LLM API")
        assert classify_llm_error(exc) is FailureClassification.RETRYABLE

    def test_generic_exception_defaults_to_retryable(self) -> None:
        exc = RuntimeError("unexpected server error 500")
        assert classify_llm_error(exc) is FailureClassification.RETRYABLE


class TestDetermineSeverity:
    @pytest.mark.parametrize("consecutive", [0, 1, 2, 3, 10])
    def test_blocking_always_critical(self, consecutive: int) -> None:
        assert determine_severity(FailureClassification.BLOCKING, consecutive) is FailureSeverity.CRITICAL

    @pytest.mark.parametrize("consecutive", [0, 1, 2, 3, 10])
    def test_rate_limited_always_error(self, consecutive: int) -> None:
        assert determine_severity(FailureClassification.RATE_LIMITED, consecutive) is FailureSeverity.ERROR

    @pytest.mark.parametrize("consecutive", [1, 2])
    def test_retryable_few_occurrences_is_warning(self, consecutive: int) -> None:
        assert determine_severity(FailureClassification.RETRYABLE, consecutive) is FailureSeverity.WARNING

    @pytest.mark.parametrize("consecutive", [3, 4, 10])
    def test_retryable_three_or_more_is_error(self, consecutive: int) -> None:
        assert determine_severity(FailureClassification.RETRYABLE, consecutive) is FailureSeverity.ERROR

    def test_retryable_zero_consecutive_is_warning(self) -> None:
        # Zero consecutive (first failure in a run) is warning
        assert determine_severity(FailureClassification.RETRYABLE, 0) is FailureSeverity.WARNING

    def test_severity_escalates_at_exactly_three(self) -> None:
        assert determine_severity(FailureClassification.RETRYABLE, 2) is FailureSeverity.WARNING
        assert determine_severity(FailureClassification.RETRYABLE, 3) is FailureSeverity.ERROR
