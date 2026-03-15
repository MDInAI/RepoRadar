from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import os
import re
from typing import Protocol

from anthropic import Anthropic
from pydantic import BaseModel, Field

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class MonetizationPotential(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReadmeBusinessAnalysis(BaseModel):
    monetization_potential: MonetizationPotential
    category: str | None = None
    agent_tags: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)


class LLMReadmeBusinessAnalysis(BaseModel):
    target_audience: str | None = None
    technical_stack: str | None = None
    open_problems: str | None = None
    competitors: str | None = None
    problem_statement: str | None = None
    target_customer: str | None = None
    product_type: str | None = None
    business_model_guess: str | None = None
    category: str | None = None
    category_confidence_score: int = 0
    agent_tags: list[str] = Field(default_factory=list)
    suggested_new_categories: list[str] = Field(default_factory=list)
    suggested_new_tags: list[str] = Field(default_factory=list)
    monetization_potential: MonetizationPotential = MonetizationPotential.LOW
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)
    confidence_score: int = 0
    recommended_action: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedReadme:
    raw_text: str
    normalized_text: str
    raw_character_count: int
    normalized_character_count: int
    removed_line_count: int


class ReadmeAnalysisProvider(Protocol):
    def analyze(self, *, repository_full_name: str, readme: NormalizedReadme) -> str: ...


class HeuristicReadmeAnalysisProvider:
    """Deterministic Story 3.3 analysis provider.

    This keeps the worker self-contained until a later story introduces an external
    model client. The job still validates the provider output through Pydantic so the
    persistence contract matches the future schema-guided path.
    """

    def analyze(self, *, repository_full_name: str, readme: NormalizedReadme) -> str:
        lower_text = readme.normalized_text.lower()
        category = _classify_category(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
        )
        agent_tags = _extract_agent_tags(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
        )
        monetization_potential = _score_monetization(lower_text=lower_text)

        pros = _dedupe(
            _extract_positive_signals(lower_text=lower_text)
            or [f"{repository_full_name} has a focused README with a clear product narrative."]
        )
        cons = _dedupe(
            _extract_risk_signals(lower_text=lower_text)
            or ["README leaves important commercial detail unspecified."]
        )
        missing_feature_signals = _dedupe(_extract_missing_feature_signals(lower_text=lower_text))

        return json.dumps(
            {
                "monetization_potential": monetization_potential.value,
                "category": category,
                "agent_tags": agent_tags[:8],
                "pros": pros[:4],
                "cons": cons[:4],
                "missing_feature_signals": missing_feature_signals[:4],
            },
            sort_keys=True,
        )


class LLMReadmeAnalysisProvider:
    """LLM-backed README analysis using Claude 3.5 Haiku."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        if not api_key:
            raise ValueError("api_key is required for LLMReadmeAnalysisProvider")
        self._client = Anthropic(api_key=api_key)
        self._model_name = model_name or "claude-3-5-haiku-20241022"

    def analyze(self, *, repository_full_name: str, readme: NormalizedReadme) -> str:
        if not readme.normalized_text.strip():
            raise ValueError("README content is empty")

        # Truncate very large READMEs to avoid context window issues
        readme_text = readme.normalized_text
        if len(readme_text) > 8000:
            readme_text = readme_text[:8000]

        categories = ["workflow", "analytics", "devops", "infrastructure", "devtools", "crm",
                      "communication", "support", "observability", "low_code", "security", "ai_ml",
                      "data", "productivity"]

        prompt = f"""Analyze this repository README and return a JSON object with business insights.

Repository: {repository_full_name}
README:
{readme_text}

Return valid JSON matching this schema:
- target_audience: who uses this (string or null)
- technical_stack: key technologies (string or null)
- open_problems: problems it solves (string or null)
- competitors: similar products (string or null)
- problem_statement: core problem addressed (string or null)
- target_customer: customer type (string or null)
- product_type: product category (string or null)
- business_model_guess: monetization approach (string or null)
- category: ONE of {categories} or null
- category_confidence_score: 0-100 integer
- agent_tags: list of relevant tags
- suggested_new_categories: categories not in controlled list
- suggested_new_tags: new tag suggestions
- monetization_potential: "low", "medium", or "high"
- pros: list of strengths (max 4)
- cons: list of weaknesses (max 4)
- missing_feature_signals: list of missing features (max 4)
- confidence_score: overall confidence 0-100 integer
- recommended_action: next step suggestion (string or null)

Return ONLY valid JSON, no markdown formatting."""

        try:
            message = self._client.messages.create(
                model=self._model_name,
                max_tokens=2048,
                timeout=30.0,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text
            validated = LLMReadmeBusinessAnalysis.model_validate_json(response_text)
            return json.dumps(validated.model_dump(), sort_keys=True)
        except Exception:
            raise


class GeminiReadmeAnalysisProvider:
    """Gemini-backed README analysis using OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model_name: str | None = None):
        if not api_key:
            raise ValueError("api_key is required for GeminiReadmeAnalysisProvider")
        if OpenAI is None:
            raise ImportError("openai package is required for GeminiReadmeAnalysisProvider")
        self._client = OpenAI(api_key=api_key, base_url=base_url or "https://api.haimaker.ai/v1")
        self._model_name = model_name or "google/gemini-2.0-flash-001"

    def analyze(self, *, repository_full_name: str, readme: NormalizedReadme) -> str:
        if not readme.normalized_text.strip():
            raise ValueError("README content is empty")

        readme_text = readme.normalized_text
        if len(readme_text) > 8000:
            readme_text = readme_text[:8000]

        categories = ["workflow", "analytics", "devops", "infrastructure", "devtools", "crm",
                      "communication", "support", "observability", "low_code", "security", "ai_ml",
                      "data", "productivity"]

        prompt = f"""Analyze this repository README and return a JSON object with business insights.

Repository: {repository_full_name}
README:
{readme_text}

Return valid JSON matching this schema:
- target_audience: who uses this (string or null)
- technical_stack: key technologies (string or null)
- open_problems: problems it solves (string or null)
- competitors: similar products (string or null)
- problem_statement: core problem addressed (string or null)
- target_customer: customer type (string or null)
- product_type: product category (string or null)
- business_model_guess: monetization approach (string or null)
- category: ONE of {categories} or null
- category_confidence_score: 0-100 integer
- agent_tags: list of relevant tags
- suggested_new_categories: categories not in controlled list
- suggested_new_tags: new tag suggestions
- monetization_potential: "low", "medium", or "high"
- pros: list of strengths (max 4)
- cons: list of weaknesses (max 4)
- missing_feature_signals: list of missing features (max 4)
- confidence_score: overall confidence 0-100 integer
- recommended_action: next step suggestion (string or null)

Return ONLY valid JSON, no markdown formatting."""

        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                timeout=30.0
            )

            response_text = response.choices[0].message.content
            if not response_text:
                raise ValueError("Empty response from Gemini API")
            # Strip markdown code blocks if present
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            validated = LLMReadmeBusinessAnalysis.model_validate_json(response_text)
            return json.dumps(validated.model_dump(), sort_keys=True)
        except Exception:
            raise


def create_analysis_provider(
    analyst_provider: str,
    anthropic_api_key: str | None = None,
    model_name: str | None = None,
    gemini_api_key: str | None = None,
    gemini_base_url: str | None = None,
    gemini_model_name: str | None = None
) -> ReadmeAnalysisProvider:
    """Factory function to create the appropriate analysis provider."""
    if analyst_provider == "llm":
        return LLMReadmeAnalysisProvider(api_key=anthropic_api_key, model_name=model_name)
    if analyst_provider == "gemini":
        return GeminiReadmeAnalysisProvider(
            api_key=gemini_api_key,
            base_url=gemini_base_url,
            model_name=gemini_model_name
        )
    return HeuristicReadmeAnalysisProvider()


def normalize_readme(raw_text: str) -> NormalizedReadme:
    lines = raw_text.splitlines()
    kept_lines: list[str] = []
    removed_line_count = 0
    skip_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if kept_lines and kept_lines[-1]:
                kept_lines.append("")
            continue

        heading = _heading_text(stripped)
        if heading is not None:
            skip_section = heading in _SKIPPED_SECTION_HEADINGS
            if skip_section:
                removed_line_count += 1
                continue
            kept_lines.append(stripped)
            continue

        if skip_section or _is_badge_line(stripped):
            removed_line_count += 1
            continue

        cleaned = _strip_markdown_noise(stripped)
        if not cleaned:
            removed_line_count += 1
            continue
        kept_lines.append(cleaned)

    normalized_text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip()
    if len(normalized_text) > 8000:
        normalized_text = normalized_text[:8000].rsplit(" ", 1)[0].rstrip()

    return NormalizedReadme(
        raw_text=raw_text,
        normalized_text=normalized_text,
        raw_character_count=len(raw_text),
        normalized_character_count=len(normalized_text),
        removed_line_count=removed_line_count,
    )


_SKIPPED_SECTION_HEADINGS = {
    "license",
    "contributing",
    "contributors",
    "acknowledgements",
    "acknowledgments",
    "development",
    "testing",
    "installation",
    "setup",
    "how to run",
    "code of conduct",
}

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "workflow": ("workflow", "approval", "automation", "orchestrat", "business process"),
    "analytics": ("analytics", "dashboard", "insight", "reporting", "metric", "bi "),
    "devops": ("ci/cd", "deploy", "kubernetes", "infra as code", "devops", "pipeline"),
    "infrastructure": ("gateway", "proxy", "database", "storage", "infrastructure", "cluster"),
    "devtools": ("developer", "sdk", "cli", "tooling", "framework", "plugin"),
    "crm": ("crm", "customer relationship", "sales", "lead", "pipeline", "account"),
    "communication": ("chat", "message", "email", "notification", "communication", "slack"),
    "support": ("ticket", "helpdesk", "support", "knowledge base", "incident response"),
    "observability": ("observability", "monitoring", "tracing", "logging", "metrics"),
    "low_code": ("no-code", "no code", "low-code", "low code", "builder", "form builder"),
    "security": ("security", "authentication", "authorization", "sso", "compliance"),
    "ai_ml": ("machine learning", "ml", "llm", "ai ", "embedding", "model"),
    "data": ("etl", "warehouse", "data pipeline", "data sync", "schema", "lineage"),
    "productivity": ("productivity", "project management", "task management", "notes"),
}

_AGENT_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "workflow": ("workflow", "approval", "orchestrat"),
    "automation": ("automation", "automate"),
    "analytics": ("analytics", "dashboard", "reporting", "insight"),
    "embedded": ("embedded", "widget", "sdk"),
    "crm": ("crm", "sales", "lead"),
    "b2b": ("enterprise", "team", "b2b", "customer"),
    "devops": ("devops", "ci/cd", "deploy", "infrastructure"),
    "support": ("support", "ticket", "helpdesk"),
    "communication": ("message", "email", "chat", "notification"),
    "monitoring": ("monitoring", "observability", "tracing", "logging"),
    "api": ("api", "rest", "graphql", "webhook"),
    "gateway": ("gateway", "proxy"),
    "data": ("etl", "warehouse", "lineage", "schema"),
    "database": ("database", "postgres", "mysql", "sqlite"),
    "migration": ("migration", "schema", "sync"),
    "forms": ("form", "builder"),
    "low-code": ("low-code", "low code", "no-code", "no code"),
    "approval": ("approval", "approve"),
    "lineage": ("lineage",),
    "ticketing": ("ticket", "helpdesk"),
}


def _heading_text(line: str) -> str | None:
    if not line.startswith("#"):
        return None
    return line.lstrip("#").strip().lower()


def _is_badge_line(line: str) -> bool:
    return line.startswith("[![") or line.startswith("![")


def _strip_markdown_noise(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _score_monetization(*, lower_text: str) -> MonetizationPotential:
    high_signals = (
        "pricing",
        "subscription",
        "enterprise",
        "customers",
        "billing",
        "revenue",
        "paid",
        "b2b",
        "saas",
    )
    medium_signals = (
        "team",
        "teams",
        "workflow",
        "automation",
        "dashboard",
        "analytics",
        "platform",
        "api",
    )
    high_count = sum(signal in lower_text for signal in high_signals)
    medium_count = sum(signal in lower_text for signal in medium_signals)
    if high_count >= 2 or (high_count >= 1 and medium_count >= 2):
        return MonetizationPotential.HIGH
    if high_count >= 1 or medium_count >= 2:
        return MonetizationPotential.MEDIUM
    return MonetizationPotential.LOW


def _classify_category(*, repository_full_name: str, lower_text: str) -> str | None:
    search_text = f"{repository_full_name.lower()} {lower_text}"
    best_category: str | None = None
    best_score = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(keyword in search_text for keyword in keywords)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category if best_score > 0 else None


def _extract_agent_tags(*, repository_full_name: str, lower_text: str) -> list[str]:
    search_text = f"{repository_full_name.lower()} {lower_text}"
    tags = [
        tag for tag, keywords in _AGENT_TAG_KEYWORDS.items() if any(keyword in search_text for keyword in keywords)
    ]
    return _dedupe(tags)


def _extract_positive_signals(*, lower_text: str) -> list[str]:
    signals: list[str] = []
    if "api" in lower_text or "integration" in lower_text:
        signals.append("README shows an integration or API-oriented product surface.")
    if "team" in lower_text or "collabor" in lower_text:
        signals.append("README targets a team workflow instead of a one-off utility.")
    if "automation" in lower_text or "workflow" in lower_text:
        signals.append("README positions the product around repeatable automation value.")
    if "analytics" in lower_text or "insight" in lower_text or "dashboard" in lower_text:
        signals.append("README describes measurable outcomes or reporting value.")
    return signals


def _extract_risk_signals(*, lower_text: str) -> list[str]:
    signals: list[str] = []
    if "pricing" not in lower_text and "paid" not in lower_text and "subscription" not in lower_text:
        signals.append("README does not explain pricing or a direct monetization path.")
    if "customer" not in lower_text and "team" not in lower_text and "user" not in lower_text:
        signals.append("README does not clearly name the target customer or operator.")
    if "security" not in lower_text and "compliance" not in lower_text:
        signals.append("README does not mention trust, security, or compliance signals.")
    if "roadmap" not in lower_text and "planned" not in lower_text:
        signals.append("README does not show a roadmap or maturity signal for future value.")
    return signals


def _extract_missing_feature_signals(*, lower_text: str) -> list[str]:
    signals: list[str] = []
    if "pricing" not in lower_text and "billing" not in lower_text:
        signals.append("Missing pricing, billing, or packaging detail.")
    if "integration" not in lower_text and "api" not in lower_text:
        signals.append("Missing ecosystem integrations or API extensibility signal.")
    if "team" not in lower_text and "workspace" not in lower_text and "collabor" not in lower_text:
        signals.append("Missing collaboration or workspace workflow detail.")
    if "analytics" not in lower_text and "report" not in lower_text:
        signals.append("Missing analytics or reporting story.")
    return signals


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
