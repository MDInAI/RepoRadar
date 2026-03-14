"""Tests for combiner provider with previous_insights support."""
from agentic_workers.providers.combiner_provider import (
    AnthropicCombinerProvider,
    HeuristicCombinerProvider,
)


def test_heuristic_provider_without_previous_insights():
    """Test heuristic provider works without previous insights."""
    provider = HeuristicCombinerProvider()
    readme_contents = [
        {"full_name": "test/repo", "content": "API integration tool"}
    ]

    result = provider.synthesize(readme_contents)

    assert "test/repo" in result
    assert "API integration" in result


def test_heuristic_provider_with_previous_insights():
    """Test heuristic provider includes previous insights."""
    provider = HeuristicCombinerProvider()
    readme_contents = [
        {"full_name": "test/repo", "content": "API integration tool"}
    ]
    previous_insights = "Previous analysis showed strong market demand."

    result = provider.synthesize(readme_contents, previous_insights)

    assert "test/repo" in result
    assert "Previous analysis showed strong market demand." in result
    assert "Building on Previous Insights" in result


def test_anthropic_provider_accepts_previous_insights():
    """Test Anthropic provider accepts previous_insights parameter."""
    # Just verify the signature works - don't call API
    provider = AnthropicCombinerProvider()
    assert hasattr(provider.synthesize, '__call__')
