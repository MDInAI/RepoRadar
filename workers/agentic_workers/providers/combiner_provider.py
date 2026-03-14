from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Protocol

from anthropic import Anthropic


@dataclass(frozen=True, slots=True)
class CombinerSynthesisResult:
    output_text: str
    provider_name: str
    model_name: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int


class CombinerProvider(Protocol):
    def synthesize(
        self,
        readme_contents: list[dict],
        previous_insights: str | None = None,
    ) -> CombinerSynthesisResult: ...


class AnthropicCombinerProvider:
    """LLM-backed combiner using Anthropic Claude."""

    MODEL_NAME = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def synthesize(
        self,
        readme_contents: list[dict],
        previous_insights: str | None = None,
    ) -> CombinerSynthesisResult:
        if not readme_contents:
            return CombinerSynthesisResult(
                output_text="No repositories provided for synthesis.",
                provider_name="anthropic",
                model_name=self.MODEL_NAME,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )

        # Build prompt with README contents
        readme_sections = []
        for idx, repo in enumerate(readme_contents, 1):
            readme_sections.append(f"## Repository {idx}: {repo['full_name']}\n\n{repo['content']}")

        # Add previous insights context if available
        context_section = ""
        if previous_insights:
            context_section = f"""
## Previous Insights

{previous_insights}

Use these previous insights to build upon and refine your analysis.

"""

        prompt = f"""Given these {len(readme_contents)} repository READMEs, propose a composite business opportunity that combines their strengths.
{context_section}
{chr(10).join(readme_sections)}

Provide a concise synthesis (200-400 words) covering:
1. What composite opportunity emerges from combining these projects
2. Key value proposition for potential customers
3. Market positioning and differentiation
4. Next steps for validation"""

        message = self._client.messages.create(
            model=self.MODEL_NAME,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        usage = getattr(message, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return CombinerSynthesisResult(
            output_text=message.content[0].text,
            provider_name="anthropic",
            model_name=self.MODEL_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )


class HeuristicCombinerProvider:
    """Minimal combiner that generates synthesis from README analysis.

    Uses pattern matching and heuristics to propose composite opportunities.
    """

    def synthesize(
        self,
        readme_contents: list[dict],
        previous_insights: str | None = None,
    ) -> CombinerSynthesisResult:
        if not readme_contents:
            return CombinerSynthesisResult(
                output_text="No repositories provided for synthesis.",
                provider_name="heuristic-combiner",
                model_name=None,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )

        repo_names = [r["full_name"] for r in readme_contents]
        combined_text = "\n\n".join([r["content"] for r in readme_contents])
        lower_text = combined_text.lower()

        # Extract key themes
        themes = []
        if "api" in lower_text or "integration" in lower_text:
            themes.append("API integration")
        if "automation" in lower_text or "workflow" in lower_text:
            themes.append("workflow automation")
        if "analytics" in lower_text or "dashboard" in lower_text:
            themes.append("analytics and insights")
        if "team" in lower_text or "collaboration" in lower_text:
            themes.append("team collaboration")

        # Build synthesis
        lines = [
            f"# Composite Opportunity: {' + '.join(repo_names)}",
            "",
            "## Overview",
            f"This synthesis combines {len(readme_contents)} repositories to create a unified business opportunity.",
            "",
        ]

        if previous_insights:
            lines.extend([
                "## Building on Previous Insights",
                previous_insights,
                "",
            ])

        if themes:
            lines.extend([
                "## Key Themes",
                *[f"- {theme}" for theme in themes],
                "",
            ])

        lines.extend([
            "## Proposed Value Proposition",
            "By combining these repositories, we can offer an integrated solution that:",
            "- Reduces integration complexity for end users",
            "- Provides a unified workflow across multiple capabilities",
            "- Creates network effects through combined feature sets",
            "",
            "## Next Steps",
            "- Validate market demand for integrated solution",
            "- Assess technical feasibility of integration",
            "- Define pricing and packaging strategy",
        ])

        return CombinerSynthesisResult(
            output_text="\n".join(lines),
            provider_name="heuristic-combiner",
            model_name=None,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )


class RetryableCombinerProvider:
    """Wraps a combiner provider with retry logic and exponential backoff."""

    def __init__(self, provider: CombinerProvider, max_retries: int = 3):
        self._provider = provider
        self._max_retries = max_retries

    def synthesize(
        self,
        readme_contents: list[dict],
        previous_insights: str | None = None,
    ) -> CombinerSynthesisResult:
        last_error = None

        for attempt in range(self._max_retries):
            try:
                return self._provider.synthesize(readme_contents, previous_insights)
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    delay = 2 ** attempt
                    time.sleep(delay)

        raise RuntimeError(f"Synthesis failed after {self._max_retries} attempts") from last_error
