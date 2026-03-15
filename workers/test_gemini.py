"""Quick test for Gemini provider."""
from agentic_workers.providers.readme_analyst import (
    GeminiReadmeAnalysisProvider,
    NormalizedReadme,
)

# Test with your Gemini configuration
provider = GeminiReadmeAnalysisProvider(
    api_key="sk-0GF-Jca5vbkmGSKnS3w5PA",
    base_url="https://api.haimaker.ai/v1",
    model_name="google/gemini-2.0-flash-001"
)

# Create a test README
test_readme = NormalizedReadme(
    raw_text="# Test Workflow Tool\n\nA simple workflow automation tool for teams.",
    normalized_text="Test Workflow Tool\n\nA simple workflow automation tool for teams.",
    raw_character_count=70,
    normalized_character_count=65,
    removed_line_count=0,
)

# Test the analysis
print("Testing Gemini provider...")
result = provider.analyze(repository_full_name="test/workflow-tool", readme=test_readme)
print("Success! Result:")
print(result[:200] + "..." if len(result) > 200 else result)
