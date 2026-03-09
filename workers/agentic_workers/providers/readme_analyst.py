from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import re
from typing import Protocol

from pydantic import BaseModel, Field


class MonetizationPotential(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReadmeBusinessAnalysis(BaseModel):
    monetization_potential: MonetizationPotential
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)


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
                "pros": pros[:4],
                "cons": cons[:4],
                "missing_feature_signals": missing_feature_signals[:4],
            },
            sort_keys=True,
        )


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
