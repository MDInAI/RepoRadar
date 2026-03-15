"""Tests for LLM README analysis provider."""
from unittest.mock import Mock, patch
import pytest
from pydantic import ValidationError

from agentic_workers.providers.readme_analyst import (
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

    with patch("agentic_workers.providers.readme_analyst.Anthropic") as mock_anthropic:
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        provider = LLMReadmeAnalysisProvider(api_key="test-key")
        result = provider.analyze(repository_full_name="test/repo", readme=sample_readme)

        assert isinstance(result, str)
        assert "workflow" in result


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


def test_create_analysis_provider_llm():
    """Test factory creates LLM provider when specified."""
    provider = create_analysis_provider("llm", "test-key", "test-model")
    assert isinstance(provider, LLMReadmeAnalysisProvider)


def test_create_analysis_provider_heuristic():
    """Test factory creates heuristic provider by default."""
    from agentic_workers.providers.readme_analyst import HeuristicReadmeAnalysisProvider
    provider = create_analysis_provider("heuristic")
    assert isinstance(provider, HeuristicReadmeAnalysisProvider)
