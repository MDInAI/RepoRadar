"""Tests for LLM README analysis provider."""
from unittest.mock import Mock, patch
import pytest
from pydantic import ValidationError

from agentic_workers.providers.readme_analyst import (
    CONTROLLED_AGENT_TAGS,
    GeminiReadmeAnalysisProvider,
    HeuristicReadmeAnalysisProvider,
    LLMReadmeAnalysisProvider,
    LLMReadmeBusinessAnalysis,
    NormalizedReadme,
    create_analysis_provider,
)


@pytest.fixture
def sample_readme():
    return NormalizedReadme(
        raw_text="# Test Project\n\nA workflow automation tool.",
        normalized_text="Test Project\n\nA workflow automation tool.",
        raw_character_count=50,
        normalized_character_count=45,
        removed_line_count=0,
    )


def test_valid_json_response(sample_readme):
    """Test that valid JSON response is parsed successfully."""
    mock_response = Mock()
    mock_response.content = [Mock(text='{"target_audience": "developers", "category": "workflow", "category_confidence_score": 85, "confidence_score": 80, "monetization_potential": "medium"}')]
    mock_response.usage = Mock(input_tokens=123, output_tokens=45)

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert isinstance(result, str)
        assert "workflow" in result
        assert provider.last_usage.input_tokens == 123
        assert provider.last_usage.output_tokens == 45
        assert provider.last_usage.total_tokens == 168


def test_valid_json_response_with_code_fences(sample_readme):
    """Test that fenced JSON is normalized before validation."""
    mock_response = Mock()
    mock_response.content = [Mock(text='```json\n{"category": "workflow", "category_confidence_score": 85, "confidence_score": 80, "monetization_potential": "medium"}\n```')]
    mock_response.usage = Mock(input_tokens=10, output_tokens=5)

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert '"category": "workflow"' in result


def test_invalid_json_raises_validation_error(sample_readme):
    """Test that invalid JSON raises ValidationError."""
    mock_response = Mock()
    mock_response.content = [Mock(text='not valid json at all')]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")

        with pytest.raises(ValidationError):
            provider.analyze(repository_full_name="test/repo", readme=sample_readme)


def test_invalid_json_is_repaired_before_raising_validation_error(sample_readme):
    initial_response = Mock()
    initial_response.content = [
        Mock(
            text=(
                '{\n'
                '  "category": "workflow"\n'
                '  "category_confidence_score": 85,\n'
                '  "confidence_score": 80,\n'
                '  "monetization_potential": "medium"\n'
                '}'
            )
        )
    ]
    initial_response.usage = Mock(input_tokens=20, output_tokens=10)

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = initial_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert '"category": "workflow"' in result
        assert mock_client.messages.create.call_count == 1
        assert provider.last_usage.total_tokens == 30


def test_invalid_field_type_raises_validation_error(sample_readme):
    """Test that invalid field types raise ValidationError."""
    mock_response = Mock()
    mock_response.content = [Mock(text='{"confidence_score": "not an integer"}')]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")

        with pytest.raises(ValidationError):
            provider.analyze(repository_full_name="test/repo", readme=sample_readme)


def test_category_from_controlled_vocabulary(sample_readme):
    """Test that category is from controlled vocabulary."""
    mock_response = Mock()
    mock_response.content = [Mock(text='{"category": "workflow", "category_confidence_score": 90, "confidence_score": 85, "monetization_potential": "high"}')]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert "workflow" in result


def test_suggested_new_categories_captured(sample_readme):
    """Test that suggested new categories are captured separately."""
    mock_response = Mock()
    mock_response.content = [Mock(text='{"category": "workflow", "suggested_new_categories": ["blockchain", "web3"], "category_confidence_score": 75, "confidence_score": 70, "monetization_potential": "medium"}')]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert "suggested_new_categories" in result
        assert "blockchain" in result


def test_unknown_agent_tags_are_redirected_to_suggested_new_tags(sample_readme):
    mock_response = Mock()
    mock_response.content = [
        Mock(
            text=(
                '{"category": "workflow", "agent_tags": ["API", "Vertical SaaS", "workflow"], '
                '"suggested_new_tags": ["Custom Workflow"], "category_confidence_score": 75, '
                '"confidence_score": 70, "monetization_potential": "medium"}'
            )
        )
    ]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = LLMReadmeBusinessAnalysis.model_validate_json(
            provider.analyze(repository_full_name="test/repo", readme=sample_readme)
        )

        assert result.agent_tags == ["api", "workflow"]
        assert result.suggested_new_tags == ["vertical-saas", "custom-workflow"]
        assert set(result.agent_tags).issubset(set(CONTROLLED_AGENT_TAGS))


def test_unknown_category_is_redirected_to_suggested_new_categories(sample_readme):
    mock_response = Mock()
    mock_response.content = [
        Mock(
            text=(
                '{"category": "education", "suggested_new_categories": ["edtech"], '
                '"category_confidence_score": 72, "confidence_score": 68, '
                '"monetization_potential": "medium"}'
            )
        )
    ]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = LLMReadmeBusinessAnalysis.model_validate_json(
            provider.analyze(repository_full_name="test/repo", readme=sample_readme)
        )

        assert result.category is None
        assert result.suggested_new_categories == ["education", "edtech"]


def test_create_analysis_provider_llm():
    """Test factory creates LLM provider when specified."""
    provider = create_analysis_provider("llm", "test-key", "test-model")
    assert isinstance(provider, LLMReadmeAnalysisProvider)
    assert provider.provider_name == "anthropic"
    assert provider.model_name == "test-model"


def test_create_analysis_provider_heuristic():
    """Test factory creates heuristic provider by default."""
    provider = create_analysis_provider("heuristic")
    assert isinstance(provider, HeuristicReadmeAnalysisProvider)
    assert provider.provider_name == "heuristic-readme-analysis"
    assert provider.model_name is None


def test_gemini_provider_rotates_to_next_key_on_daily_limit(sample_readme):
    class FakeGeminiError(Exception):
        def __init__(self, message: str, status_code: int) -> None:
            super().__init__(message)
            self.status_code = status_code

    class FakeCompletions:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def create(self, **_kwargs):
            if self.api_key == "key-1":
                raise FakeGeminiError(
                    "Authentication Error: Daily request limit reached. Free accounts are limited to 500 requests per day.",
                    401,
                )
            response = Mock()
            response.choices = [
                Mock(
                    message=Mock(
                        content='{"category": "workflow", "category_confidence_score": 84, "confidence_score": 79, "monetization_potential": "medium"}'
                    )
                )
            ]
            response.usage = Mock(prompt_tokens=40, completion_tokens=12, total_tokens=52)
            return response

    class FakeOpenAIClient:
        def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
            del base_url
            self.chat = Mock(completions=FakeCompletions(api_key))

    with patch("agentic_workers.providers.readme_analyst.OpenAI", FakeOpenAIClient):
        provider = GeminiReadmeAnalysisProvider(
            api_keys=("key-1", "key-2"),
            base_url="https://example.invalid/v1",
            model_name="gemini-test",
        )
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert '"category": "workflow"' in result
        assert provider.last_usage.total_tokens == 52


def test_invalid_category_outside_controlled_vocabulary_becomes_suggestion(sample_readme):
    """Test that uncontrolled categories are redirected into suggestions instead of failing the run."""
    mock_response = Mock()
    mock_response.content = [Mock(text='{"category": "blockchain", "confidence_score": 80, "monetization_potential": "medium"}')]

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = LLMReadmeBusinessAnalysis.model_validate_json(
            provider.analyze(repository_full_name="test/repo", readme=sample_readme)
        )

        assert result.category is None
        assert result.suggested_new_categories == ["blockchain"]


def test_heuristic_provider_uses_evidence_and_emits_real_confidence(sample_readme):
    provider = HeuristicReadmeAnalysisProvider()

    result = LLMReadmeBusinessAnalysis.model_validate_json(
        provider.analyze(
            repository_full_name="acme/ops-platform",
            readme=sample_readme,
            evidence={
                "evidence_summary": "Repository exposes API, auth, frontend, backend, and deployment signals.",
                "signals": {
                    "has_api_surface": True,
                    "has_auth_signals": True,
                    "has_frontend_surface": True,
                    "has_backend_surface": True,
                    "has_containerization": True,
                    "has_deploy_config": True,
                    "readme_mentions_team": True,
                    "readme_mentions_enterprise": True,
                    "framework_signals": ["react", "nextjs", "postgres", "docker"],
                    "primary_languages": ["typescript"],
                    "repository_description_present": True,
                    "readme_length": 420,
                },
                "score_breakdown": {
                    "technical_maturity_score": 72,
                    "commercial_readiness_score": 76,
                    "hosted_gap_score": 68,
                    "market_timing_score": 61,
                },
                "supporting_signals": ["Release history suggests maintainers ship packaged milestones."],
                "red_flags": [],
                "contradictions": [],
                "missing_information": [],
            },
        )
    )

    assert result.category in {"workflow", "devtools"}
    assert result.category_confidence_score >= 60
    assert result.confidence_score >= 60
    assert "api" in result.agent_tags
    assert "auth" in result.agent_tags
    assert "commercial-ready" in result.agent_tags
    assert result.suggested_new_tags == []


def test_heuristic_provider_does_not_false_positive_forms_from_platform(sample_readme):
    provider = HeuristicReadmeAnalysisProvider()
    platform_readme = NormalizedReadme(
        raw_text="# Platform\n\nOpen platform for APIs and integrations.",
        normalized_text="Platform\n\nOpen platform for APIs and integrations.",
        raw_character_count=48,
        normalized_character_count=48,
        removed_line_count=0,
    )

    result = LLMReadmeBusinessAnalysis.model_validate_json(
        provider.analyze(
            repository_full_name="acme/platform-core",
            readme=platform_readme,
            evidence={
                "signals": {
                    "has_api_surface": True,
                    "readme_length": 48,
                },
                "score_breakdown": {},
            },
        )
    )

    assert "forms" not in result.agent_tags
    assert "forms" not in result.suggested_new_tags


def test_new_common_taxonomy_tags_are_canonical(sample_readme):
    assert "forms" in CONTROLLED_AGENT_TAGS
    assert "gateway" in CONTROLLED_AGENT_TAGS
    assert "embedded" in CONTROLLED_AGENT_TAGS
    assert "migration" in CONTROLLED_AGENT_TAGS
