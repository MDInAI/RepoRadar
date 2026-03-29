from __future__ import annotations

import os
import re
from dataclasses import dataclass

from anthropic import Anthropic

from agentic_workers.providers.combiner_provider import CombinerSynthesisResult

_SYSTEM_PROMPT = """\
You are a senior research analyst and systems architect. You are given README files \
and analysis summaries from multiple open-source repositories, all related to a common \
theme chosen by the user.

Your job is to produce a comprehensive strategic synthesis that:
1. Catalogs each repository's approach, architecture, and key innovations
2. Compares and ranks approaches (what works best, what doesn't)
3. Identifies the best components and ideas from across all repos
4. Proposes an ideal architecture that combines the best of everything
5. Identifies gaps — what's missing from existing solutions
6. Suggests a concrete roadmap with phases
7. Notes future opportunities and research directions

Be thorough, specific, and opinionated. Cite specific repositories when making claims.
Output in markdown.\
"""

_USER_PROMPT_TEMPLATE = """\
## Research Context

The user's research focus: {idea_text}

## Repositories Under Analysis ({repo_count} total)

{repo_sections}
{previous_insights_section}
---

Produce your deep synthesis now. Be comprehensive — this is a strategic research \
document, not a summary. The user wants to build the best possible solution by \
learning from all of these projects.\
"""

_README_TRUNCATION_CHARS = 4000


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated ...]"


def _build_repo_section(idx: int, repo: dict) -> str:
    full_name = repo.get("full_name", f"repo-{idx}")
    content = repo.get("content", "")
    analysis = repo.get("analysis", "")

    parts = [f"### {idx}. {full_name}\n"]
    parts.append(_truncate(content, _README_TRUNCATION_CHARS))
    if analysis:
        parts.append(f"\n**Analysis Summary:**\n{_truncate(analysis, 1000)}")
    return "\n".join(parts)


def _extract_title(text: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _extract_summary(text: str) -> str | None:
    # Try to find an "Executive Summary" or "Overview" section
    m = re.search(
        r"^#{1,3}\s+(?:Executive Summary|Overview|Summary)\s*\n+([\s\S]+?)(?=\n#{1,3}\s|\Z)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Fallback: first non-heading paragraph
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _extract_key_insights(text: str) -> list[str] | None:
    m = re.search(
        r"^#{1,3}\s+(?:Key (?:Findings|Insights|Recommendations|Takeaways))\s*\n+([\s\S]+?)(?=\n#{1,3}\s|\Z)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    if not m:
        return None
    bullets = re.findall(r"^[-*]\s+(.+)$", m.group(1), re.MULTILINE)
    return bullets[:10] if bullets else None


class DeepSynthesisProvider:
    """Claude Opus provider for deep comparative synthesis of many repositories."""

    MODEL_NAME = "claude-opus-4-20250514"
    EXTENDED_THINKING_BUDGET = 10_000

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def synthesize(
        self,
        repo_contents: list[dict],
        idea_text: str,
        previous_insights: str | None = None,
    ) -> CombinerSynthesisResult:
        if not repo_contents:
            return CombinerSynthesisResult(
                output_text="No repositories provided for deep synthesis.",
                provider_name="anthropic-deep-synthesis",
                model_name=self.MODEL_NAME,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            )

        repo_sections = "\n\n".join(
            _build_repo_section(idx, repo)
            for idx, repo in enumerate(repo_contents, 1)
        )

        previous_insights_section = ""
        if previous_insights:
            previous_insights_section = (
                f"\n## Previous Insights\n\n{previous_insights}\n\n"
                "Build upon these findings in your synthesis.\n"
            )

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            idea_text=idea_text,
            repo_count=len(repo_contents),
            repo_sections=repo_sections,
            previous_insights_section=previous_insights_section,
        )

        response = self._client.messages.create(
            model=self.MODEL_NAME,
            max_tokens=16_000,
            thinking={"type": "enabled", "budget_tokens": self.EXTENDED_THINKING_BUDGET},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        output_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                output_text = block.text
                break

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        return CombinerSynthesisResult(
            output_text=output_text,
            provider_name="anthropic-deep-synthesis",
            model_name=self.MODEL_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )


def parse_deep_synthesis_output(output: str) -> dict:
    """Extract structured fields from deep synthesis markdown output."""
    return {
        "title": _extract_title(output),
        "summary": _extract_summary(output),
        "key_insights": _extract_key_insights(output),
    }
