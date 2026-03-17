from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Callable, Protocol

from anthropic import Anthropic
from pydantic import BaseModel, Field, field_validator, model_validator

from agentic_workers.storage.gemini_key_pool_snapshots import write_gemini_key_pool_snapshot

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class MonetizationPotential(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


CONTROLLED_REPOSITORY_CATEGORIES = (
    "workflow",
    "analytics",
    "devops",
    "infrastructure",
    "devtools",
    "crm",
    "communication",
    "support",
    "observability",
    "low_code",
    "security",
    "ai_ml",
    "data",
    "productivity",
)

CONTROLLED_AGENT_TAGS = (
    "admin-panel",
    "approval",
    "analytics",
    "api",
    "auth",
    "automation",
    "b2b",
    "b2c",
    "billing",
    "commercial-ready",
    "communication",
    "crm",
    "data",
    "database",
    "developer",
    "devops",
    "docker",
    "embedded",
    "enterprise",
    "forms",
    "gateway",
    "go",
    "hosted-gap",
    "integrations",
    "internal-tools",
    "kubernetes",
    "lineage",
    "low-code",
    "low-confidence",
    "maintainer-risk",
    "marketplace",
    "migration",
    "monitoring",
    "multi-tenant",
    "needs-deep-analysis",
    "nextjs",
    "notifications",
    "open-core-candidate",
    "platform",
    "plugin-ecosystem",
    "postgres",
    "python",
    "react",
    "reporting",
    "saas-candidate",
    "self-hosted",
    "smb",
    "support",
    "ticketing",
    "typescript",
    "workflow",
)


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
    category_confidence_score: int = Field(default=0, ge=0, le=100)
    agent_tags: list[str] = Field(default_factory=list)
    suggested_new_categories: list[str] = Field(default_factory=list)
    suggested_new_tags: list[str] = Field(default_factory=list)
    monetization_potential: MonetizationPotential = MonetizationPotential.LOW
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    missing_feature_signals: list[str] = Field(default_factory=list)
    confidence_score: int = Field(default=0, ge=0, le=100)
    recommended_action: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("category must be a string or null")
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized not in CONTROLLED_REPOSITORY_CATEGORIES:
            raise ValueError(
                f"category must be one of {CONTROLLED_REPOSITORY_CATEGORIES!r} or null"
            )
        return normalized

    @field_validator(
        "agent_tags",
        "suggested_new_categories",
        "suggested_new_tags",
        "pros",
        "cons",
        "missing_feature_signals",
        mode="before",
    )
    @classmethod
    def _normalize_string_lists(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("value must be a list")

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_item in value:
            if not isinstance(raw_item, str):
                raise TypeError("list items must be strings")
            candidate = raw_item.strip()
            if not candidate:
                continue
            dedupe_key = candidate.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(candidate)
        return normalized

    @field_validator(
        "target_audience",
        "technical_stack",
        "open_problems",
        "competitors",
        "problem_statement",
        "target_customer",
        "product_type",
        "business_model_guess",
        "recommended_action",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("value must be a string or null")
        candidate = re.sub(r"\s+", " ", value).strip()
        return candidate or None

    @model_validator(mode="after")
    def _normalize_taxonomy_fields(self) -> "LLMReadmeBusinessAnalysis":
        normalized_tags: list[str] = []
        suggested_tags: list[str] = []
        seen_tags: set[str] = set()
        seen_suggested_tags: set[str] = set()

        for raw_tag in [*self.agent_tags, *self.suggested_new_tags]:
            normalized = _normalize_tag_candidate(raw_tag)
            if not normalized:
                continue
            if normalized in CONTROLLED_AGENT_TAGS:
                if normalized not in seen_tags:
                    seen_tags.add(normalized)
                    normalized_tags.append(normalized)
                continue
            if normalized not in seen_suggested_tags:
                seen_suggested_tags.add(normalized)
                suggested_tags.append(normalized)

        normalized_categories: list[str] = []
        seen_categories: set[str] = set()
        for raw_category in self.suggested_new_categories:
            normalized = _normalize_category_candidate(raw_category)
            if not normalized or normalized in CONTROLLED_REPOSITORY_CATEGORIES:
                continue
            if normalized in seen_categories:
                continue
            seen_categories.add(normalized)
            normalized_categories.append(normalized)

        self.agent_tags = normalized_tags
        self.suggested_new_tags = suggested_tags
        self.suggested_new_categories = normalized_categories
        return self


@dataclass(frozen=True, slots=True)
class NormalizedReadme:
    raw_text: str
    normalized_text: str
    raw_character_count: int
    normalized_character_count: int
    removed_line_count: int


@dataclass(frozen=True, slots=True)
class ReadmeAnalysisUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class GeminiKeySelection:
    label: str
    api_key: str


@dataclass(slots=True)
class GeminiKeyState:
    label: str
    api_key: str
    last_used_at: datetime | None = None
    cooldown_until: datetime | None = None
    last_error: str | None = None
    last_status: str = "idle"
    last_response_status: int | None = None


class GeminiKeyPool:
    def __init__(self, api_keys: tuple[str, ...] | list[str]) -> None:
        configured_keys = [key for key in api_keys if isinstance(key, str) and key.strip()]
        if not configured_keys:
            raise ValueError("At least one Gemini API key is required")
        self._states = [
            GeminiKeyState(label=f"key-{index + 1}", api_key=key.strip())
            for index, key in enumerate(configured_keys)
        ]
        self._next_index = 0

    def select(self) -> GeminiKeySelection:
        now = datetime.now(timezone.utc)
        healthy_states = [
            state for state in self._states if state.cooldown_until is None or state.cooldown_until <= now
        ]
        candidate_states = healthy_states or self._states
        selected = candidate_states[self._next_index % len(candidate_states)]
        self._next_index += 1
        selected.last_used_at = now
        if selected.cooldown_until is not None and selected.cooldown_until <= now:
            selected.cooldown_until = None
            selected.last_status = "healthy"
            selected.last_error = None
            selected.last_response_status = None
        return GeminiKeySelection(label=selected.label, api_key=selected.api_key)

    def mark_success(self, label: str) -> None:
        state = self._state_by_label(label)
        if state is None:
            return
        state.cooldown_until = None
        state.last_error = None
        state.last_status = "healthy"
        state.last_response_status = 200

    def mark_cooldown(
        self,
        *,
        label: str,
        error_message: str,
        status_code: int | None,
        cooldown_seconds: int,
        status_label: str,
    ) -> None:
        state = self._state_by_label(label)
        if state is None:
            return
        state.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=max(cooldown_seconds, 1))
        state.last_error = error_message
        state.last_status = status_label
        state.last_response_status = status_code

    def snapshot_payload(self) -> list[dict[str, object]]:
        return [
            {
                "label": state.label,
                "status": state.last_status,
                "last_used_at": state.last_used_at.isoformat() if state.last_used_at is not None else None,
                "cooldown_until": state.cooldown_until.isoformat()
                if state.cooldown_until is not None
                else None,
                "last_error": state.last_error,
                "last_response_status": state.last_response_status,
            }
            for state in self._states
        ]

    def key_count(self) -> int:
        return len(self._states)

    def _state_by_label(self, label: str) -> GeminiKeyState | None:
        for state in self._states:
            if state.label == label:
                return state
        return None


@dataclass(frozen=True, slots=True)
class HeuristicEvidenceSnapshot:
    summary: str
    signals: dict[str, object]
    score_breakdown: dict[str, int]
    supporting_signals: list[str]
    red_flags: list[str]
    contradictions: list[str]
    missing_information: list[str]
    insufficient_reason: str | None
    analysis_mode_target: str | None


class ReadmeAnalysisProvider(Protocol):
    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: NormalizedReadme,
        evidence: dict[str, object] | None = None,
    ) -> str: ...
    @property
    def provider_name(self) -> str: ...
    @property
    def model_name(self) -> str | None: ...
    @property
    def last_usage(self) -> ReadmeAnalysisUsage: ...


class HeuristicReadmeAnalysisProvider:
    """Deterministic Story 3.3 analysis provider.

    This keeps the worker self-contained until a later story introduces an external
    model client. The job still validates the provider output through Pydantic so the
    persistence contract matches the future schema-guided path.
    """

    def __init__(self) -> None:
        self._last_usage = ReadmeAnalysisUsage()

    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: NormalizedReadme,
        evidence: dict[str, object] | None = None,
    ) -> str:
        self._last_usage = ReadmeAnalysisUsage()
        lower_text = readme.normalized_text.lower()
        evidence_snapshot = _parse_heuristic_evidence(evidence)
        category, category_confidence_score = _classify_category(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
            evidence=evidence_snapshot,
        )
        agent_tags = _extract_agent_tags(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
            category=category,
            evidence=evidence_snapshot,
        )
        suggested_new_tags = _suggest_new_tags(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
            evidence=evidence_snapshot,
        )
        monetization_potential = _score_monetization(
            lower_text=lower_text,
            evidence=evidence_snapshot,
        )

        pros = _build_positive_signals(
            repository_full_name=repository_full_name,
            lower_text=lower_text,
            category=category,
            evidence=evidence_snapshot,
        )
        cons = _build_risk_signals(
            lower_text=lower_text,
            evidence=evidence_snapshot,
        )
        missing_feature_signals = _build_missing_feature_signals(
            lower_text=lower_text,
            evidence=evidence_snapshot,
        )
        confidence_score = _compute_confidence_score(
            readme=readme,
            category=category,
            category_confidence_score=category_confidence_score,
            agent_tags=agent_tags,
            evidence=evidence_snapshot,
        )
        target_customer = _infer_target_customer(
            agent_tags=agent_tags,
            evidence=evidence_snapshot,
        )
        product_type = _infer_product_type(category=category, agent_tags=agent_tags)
        business_model_guess = _infer_business_model(
            monetization_potential=monetization_potential,
            agent_tags=agent_tags,
            evidence=evidence_snapshot,
        )
        technical_stack = _infer_technical_stack(evidence_snapshot)
        recommended_action = _recommend_action(
            confidence_score=confidence_score,
            monetization_potential=monetization_potential,
            agent_tags=agent_tags,
            evidence=evidence_snapshot,
        )

        return json.dumps(
            {
                "target_audience": _infer_target_audience(agent_tags=agent_tags, category=category),
                "technical_stack": technical_stack,
                "open_problems": evidence_snapshot.summary or None,
                "competitors": None,
                "problem_statement": evidence_snapshot.summary or None,
                "target_customer": target_customer,
                "product_type": product_type,
                "business_model_guess": business_model_guess,
                "monetization_potential": monetization_potential.value,
                "category": category,
                "category_confidence_score": category_confidence_score,
                "agent_tags": agent_tags[:8],
                "suggested_new_categories": [],
                "suggested_new_tags": suggested_new_tags[:4],
                "pros": pros[:4],
                "cons": cons[:4],
                "missing_feature_signals": missing_feature_signals[:4],
                "confidence_score": confidence_score,
                "recommended_action": recommended_action,
            },
            sort_keys=True,
        )

    @property
    def provider_name(self) -> str:
        return "heuristic-readme-analysis"

    @property
    def model_name(self) -> str | None:
        return None

    @property
    def last_usage(self) -> ReadmeAnalysisUsage:
        return self._last_usage


class LLMReadmeAnalysisProvider:
    """LLM-backed README analysis using Claude 3.5 Haiku."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        if not api_key:
            raise ValueError("api_key is required for LLMReadmeAnalysisProvider")
        self._client = Anthropic(api_key=api_key)
        self._model_name = model_name or "claude-3-5-haiku-20241022"
        self._last_usage = ReadmeAnalysisUsage()

    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: NormalizedReadme,
        evidence: dict[str, object] | None = None,
    ) -> str:
        if not readme.normalized_text.strip():
            raise ValueError("README content is empty")

        # Truncate very large READMEs to avoid context window issues
        readme_text = readme.normalized_text
        if len(readme_text) > 8000:
            readme_text = readme_text[:8000]

        prompt = f"""Analyze this repository README and return a JSON object with business insights.

Repository: {repository_full_name}
Deterministic evidence:
{json.dumps(evidence or {}, indent=2, sort_keys=True)}

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
- category: ONE of {list(CONTROLLED_REPOSITORY_CATEGORIES)} or null
- category_confidence_score: 0-100 integer
- agent_tags: list of relevant tags chosen only from {list(CONTROLLED_AGENT_TAGS)}
- suggested_new_categories: categories not in controlled list
- suggested_new_tags: new tag suggestions not already in the controlled tag list
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

            input_tokens = _coerce_token_count(getattr(getattr(message, "usage", None), "input_tokens", 0))
            output_tokens = _coerce_token_count(getattr(getattr(message, "usage", None), "output_tokens", 0))
            response_text = _extract_anthropic_text(message)
            self._last_usage = ReadmeAnalysisUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
            validated = _validate_or_repair_analysis_output(
                response_text,
                repair_json=self._repair_json_response,
            )
            return json.dumps(validated.model_dump(), sort_keys=True)
        except Exception:
            self._last_usage = ReadmeAnalysisUsage()
            raise

    def _repair_json_response(self, invalid_json: str) -> str:
        message = self._client.messages.create(
            model=self._model_name,
            max_tokens=2048,
            timeout=30.0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Repair this malformed JSON so it becomes valid JSON matching the same intent. "
                        "Return only valid JSON with no markdown fences.\n\n"
                        f"{invalid_json}"
                    ),
                }
            ],
        )
        input_tokens = _coerce_token_count(getattr(getattr(message, "usage", None), "input_tokens", 0))
        output_tokens = _coerce_token_count(getattr(getattr(message, "usage", None), "output_tokens", 0))
        self._last_usage = ReadmeAnalysisUsage(
            input_tokens=self._last_usage.input_tokens + input_tokens,
            output_tokens=self._last_usage.output_tokens + output_tokens,
            total_tokens=self._last_usage.total_tokens + input_tokens + output_tokens,
        )
        return _extract_anthropic_text(message)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str | None:
        return self._model_name

    @property
    def last_usage(self) -> ReadmeAnalysisUsage:
        return self._last_usage


class GeminiReadmeAnalysisProvider:
    """Gemini-backed README analysis using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        api_keys: tuple[str, ...] | list[str] | None = None,
        runtime_dir: Path | None = None,
    ):
        configured_keys = [
            *(api_keys or ()),
            *( [api_key] if isinstance(api_key, str) and api_key.strip() else [] ),
        ]
        deduped_keys: list[str] = []
        seen_keys: set[str] = set()
        for raw_key in configured_keys:
            candidate = str(raw_key).strip()
            if not candidate or candidate in seen_keys:
                continue
            deduped_keys.append(candidate)
            seen_keys.add(candidate)
        if not deduped_keys:
            raise ValueError("api_key or api_keys is required for GeminiReadmeAnalysisProvider")
        if OpenAI is None:
            raise ImportError("openai package is required for GeminiReadmeAnalysisProvider")
        self._base_url = base_url or "https://api.haimaker.ai/v1"
        self._runtime_dir = runtime_dir
        self._model_name = model_name or "google/gemini-2.0-flash-001"
        self._last_usage = ReadmeAnalysisUsage()
        self._key_pool = GeminiKeyPool(deduped_keys)
        self._clients = {
            f"key-{index + 1}": OpenAI(api_key=key, base_url=self._base_url)
            for index, key in enumerate(deduped_keys)
        }
        self._write_pool_snapshot()

    def analyze(
        self,
        *,
        repository_full_name: str,
        readme: NormalizedReadme,
        evidence: dict[str, object] | None = None,
    ) -> str:
        if not readme.normalized_text.strip():
            raise ValueError("README content is empty")

        readme_text = readme.normalized_text
        if len(readme_text) > 8000:
            readme_text = readme_text[:8000]

        prompt = f"""Analyze this repository README and return a JSON object with business insights.

Repository: {repository_full_name}
Deterministic evidence:
{json.dumps(evidence or {}, indent=2, sort_keys=True)}

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
- category: ONE of {list(CONTROLLED_REPOSITORY_CATEGORIES)} or null
- category_confidence_score: 0-100 integer
- agent_tags: list of relevant tags chosen only from {list(CONTROLLED_AGENT_TAGS)}
- suggested_new_categories: categories not in controlled list
- suggested_new_tags: new tag suggestions not already in the controlled tag list
- monetization_potential: "low", "medium", or "high"
- pros: list of strengths (max 4)
- cons: list of weaknesses (max 4)
- missing_feature_signals: list of missing features (max 4)
- confidence_score: overall confidence 0-100 integer
- recommended_action: next step suggestion (string or null)

Return ONLY valid JSON, no markdown formatting."""

        last_error: Exception | None = None
        self._last_usage = ReadmeAnalysisUsage()

        for _ in range(self._key_pool.key_count()):
            selection = self._key_pool.select()
            client = self._clients[selection.label]
            try:
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                    timeout=30.0
                )

                response_text = response.choices[0].message.content
                if not response_text:
                    raise ValueError("Empty response from Gemini API")
                usage = getattr(response, "usage", None)
                input_tokens = _coerce_token_count(getattr(usage, "prompt_tokens", 0))
                output_tokens = _coerce_token_count(getattr(usage, "completion_tokens", 0))
                total_tokens = _coerce_token_count(getattr(usage, "total_tokens", input_tokens + output_tokens))
                self._last_usage = ReadmeAnalysisUsage(
                    input_tokens=self._last_usage.input_tokens + input_tokens,
                    output_tokens=self._last_usage.output_tokens + output_tokens,
                    total_tokens=self._last_usage.total_tokens + total_tokens,
                )
                validated = _validate_or_repair_analysis_output(
                    response_text,
                    repair_json=lambda invalid_json: self._repair_json_response(
                        invalid_json,
                        selection_label=selection.label,
                    ),
                )
                self._key_pool.mark_success(selection.label)
                self._write_pool_snapshot()
                return json.dumps(validated.model_dump(), sort_keys=True)
            except Exception as exc:
                if _should_rotate_gemini_key(exc):
                    self._key_pool.mark_cooldown(
                        label=selection.label,
                        error_message=str(exc),
                        status_code=_extract_openai_status_code(exc),
                        cooldown_seconds=_derive_gemini_cooldown_seconds(exc),
                        status_label=_derive_gemini_status_label(exc),
                    )
                    self._write_pool_snapshot()
                    last_error = exc
                    continue
                self._write_pool_snapshot()
                self._last_usage = ReadmeAnalysisUsage()
                raise

        self._write_pool_snapshot()
        self._last_usage = ReadmeAnalysisUsage()
        if last_error is not None:
            raise last_error
        raise RuntimeError("Gemini key pool exhausted without a usable key")

    def _repair_json_response(self, invalid_json: str, *, selection_label: str) -> str:
        client = self._clients[selection_label]
        response = client.chat.completions.create(
            model=self._model_name,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Repair this malformed JSON so it becomes valid JSON matching the same intent. "
                        "Return only valid JSON with no markdown fences.\n\n"
                        f"{invalid_json}"
                    ),
                }
            ],
            max_tokens=2048,
            timeout=30.0,
        )
        response_text = response.choices[0].message.content
        if not response_text:
            raise ValueError("Empty repair response from Gemini API")
        usage = getattr(response, "usage", None)
        input_tokens = _coerce_token_count(getattr(usage, "prompt_tokens", 0))
        output_tokens = _coerce_token_count(getattr(usage, "completion_tokens", 0))
        total_tokens = _coerce_token_count(getattr(usage, "total_tokens", input_tokens + output_tokens))
        self._last_usage = ReadmeAnalysisUsage(
            input_tokens=self._last_usage.input_tokens + input_tokens,
            output_tokens=self._last_usage.output_tokens + output_tokens,
            total_tokens=self._last_usage.total_tokens + total_tokens,
        )
        return response_text

    @property
    def provider_name(self) -> str:
        return "gemini-compatible"

    @property
    def model_name(self) -> str | None:
        return self._model_name

    @property
    def last_usage(self) -> ReadmeAnalysisUsage:
        return self._last_usage

    def _write_pool_snapshot(self) -> None:
        write_gemini_key_pool_snapshot(
            runtime_dir=self._runtime_dir,
            model_name=self._model_name,
            base_url=self._base_url,
            keys=self._key_pool.snapshot_payload(),
        )


def create_analysis_provider(
    analyst_provider: str,
    anthropic_api_key: str | None = None,
    model_name: str | None = None,
    gemini_api_key: str | None = None,
    gemini_api_keys: tuple[str, ...] | list[str] | None = None,
    gemini_base_url: str | None = None,
    gemini_model_name: str | None = None,
    runtime_dir: Path | None = None,
) -> ReadmeAnalysisProvider:
    """Factory function to create the appropriate analysis provider."""
    if analyst_provider == "llm":
        return LLMReadmeAnalysisProvider(api_key=anthropic_api_key, model_name=model_name)
    if analyst_provider == "gemini":
        return GeminiReadmeAnalysisProvider(
            api_key=gemini_api_key,
            api_keys=gemini_api_keys,
            base_url=gemini_base_url,
            model_name=gemini_model_name,
            runtime_dir=runtime_dir,
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


def _coerce_token_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _strip_json_code_fences(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```json"):
        candidate = candidate[7:]
    elif candidate.startswith("```"):
        candidate = candidate[3:]
    if candidate.endswith("```"):
        candidate = candidate[:-3]
    return candidate.strip()


def _validate_or_repair_analysis_output(
    response_text: str,
    *,
    repair_json: Callable[[str], str] | None = None,
) -> LLMReadmeBusinessAnalysis:
    candidate = _strip_json_code_fences(response_text)
    try:
        return LLMReadmeBusinessAnalysis.model_validate_json(candidate)
    except Exception as original_error:
        repaired_candidate = _attempt_local_json_repair(candidate)
        if repaired_candidate is not None:
            try:
                return LLMReadmeBusinessAnalysis.model_validate_json(repaired_candidate)
            except Exception:
                pass

        if repair_json is not None:
            repaired_remote = _strip_json_code_fences(repair_json(candidate))
            local_repaired_remote = _attempt_local_json_repair(repaired_remote) or repaired_remote
            return LLMReadmeBusinessAnalysis.model_validate_json(local_repaired_remote)
        raise original_error


def _attempt_local_json_repair(candidate: str) -> str | None:
    extracted = _extract_json_object(candidate)
    if extracted is None:
        return None

    repaired = extracted.replace("\r\n", "\n").replace("\r", "\n")
    repaired = _insert_missing_commas_between_lines(repaired)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    repaired = repaired.strip()
    return repaired or None


def _extract_json_object(candidate: str) -> str | None:
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return candidate[start : end + 1]


def _insert_missing_commas_between_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 2:
        return text

    repaired_lines: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.rstrip()
        next_line = lines[index + 1].lstrip() if index + 1 < len(lines) else ""
        if (
            stripped
            and next_line
            and not stripped.endswith(("{", "[", ",", ":"))
            and not next_line.startswith(("}", "]", ","))
        ):
            repaired_lines.append(f"{stripped},")
        else:
            repaired_lines.append(line)
    return "\n".join(repaired_lines)


def _normalize_tag_candidate(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return candidate


def _normalize_category_candidate(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return candidate


def _extract_anthropic_text(message: object) -> str:
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        raise ValueError("Anthropic response content was not a list")
    text_parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            text_parts.append(text)
    if not text_parts:
        raise ValueError("Anthropic response did not include any text content")
    return "".join(text_parts)


def _extract_openai_status_code(error: Exception) -> int | None:
    for attribute in ("status_code", "status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _should_rotate_gemini_key(error: Exception) -> bool:
    message = str(error).lower()
    status_code = _extract_openai_status_code(error)
    if any(
        phrase in message
        for phrase in (
            "daily request limit reached",
            "free accounts are limited to 500 requests per day",
            "too many requests",
            "rate limit",
            "rate_limit",
        )
    ):
        return True
    if status_code in {401, 429}:
        return True
    return False


def _derive_gemini_cooldown_seconds(error: Exception) -> int:
    message = str(error).lower()
    if "daily request limit reached" in message or "500 requests per day" in message:
        return 24 * 60 * 60
    return 15 * 60


def _derive_gemini_status_label(error: Exception) -> str:
    message = str(error).lower()
    if "daily request limit reached" in message or "500 requests per day" in message:
        return "daily-limit"
    if "rate limit" in message or "rate_limit" in message or _extract_openai_status_code(error) == 429:
        return "rate-limited"
    if _extract_openai_status_code(error) == 401:
        return "auth-error"
    return "cooldown"


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

_CATEGORY_KEYWORDS: dict[str, tuple[tuple[str, int], ...]] = {
    "workflow": (
        ("workflow", 18),
        ("workflows", 18),
        ("orchestrat*", 18),
        ("approval", 14),
        ("business process", 14),
        ("automation", 8),
    ),
    "analytics": (
        ("analytics", 18),
        ("dashboard", 14),
        ("reporting", 14),
        ("insight", 10),
        ("metric", 10),
        ("business intelligence", 16),
    ),
    "devops": (
        ("ci/cd", 18),
        ("deployment", 14),
        ("deploy", 10),
        ("kubernetes", 16),
        ("terraform", 16),
        ("helm", 12),
        ("devops", 18),
        ("pipeline", 10),
        ("infrastructure as code", 18),
    ),
    "infrastructure": (
        ("gateway", 18),
        ("proxy", 16),
        ("storage", 14),
        ("infrastructure", 12),
        ("cluster", 14),
        ("service mesh", 18),
        ("reverse proxy", 18),
    ),
    "devtools": (
        ("developer tool", 20),
        ("developer tools", 20),
        ("sdk", 18),
        ("cli", 18),
        ("tooling", 12),
        ("framework", 10),
        ("plugin", 14),
        ("library", 8),
    ),
    "crm": (
        ("crm", 20),
        ("customer relationship", 18),
        ("sales", 14),
        ("lead", 14),
        ("account", 10),
        ("customer pipeline", 14),
    ),
    "communication": (
        ("chat", 16),
        ("email", 16),
        ("message", 12),
        ("messages", 12),
        ("messaging", 16),
        ("notification", 12),
        ("notifications", 12),
        ("inbox", 12),
        ("mail", 8),
        ("slack", 10),
    ),
    "support": (
        ("support", 12),
        ("ticket", 18),
        ("tickets", 18),
        ("helpdesk", 18),
        ("knowledge base", 16),
        ("incident response", 14),
    ),
    "observability": (
        ("observability", 20),
        ("monitoring", 18),
        ("tracing", 18),
        ("logging", 16),
        ("metrics", 16),
        ("telemetry", 18),
    ),
    "low_code": (
        ("low-code", 18),
        ("low code", 18),
        ("no-code", 18),
        ("no code", 18),
        ("form builder", 16),
        ("builder", 6),
    ),
    "security": (
        ("security", 16),
        ("authentication", 16),
        ("authorization", 16),
        ("oauth", 18),
        ("sso", 18),
        ("rbac", 16),
        ("identity", 16),
        ("compliance", 14),
    ),
    "ai_ml": (
        ("machine learning", 20),
        ("llm", 20),
        ("large language model", 18),
        ("embedding", 16),
        ("embeddings", 16),
        ("rag", 16),
        ("inference", 14),
        ("transcription", 14),
        ("prompt", 10),
        ("multimodal", 14),
        ("agentic", 12),
        ("fine-tuning", 16),
    ),
    "data": (
        ("etl", 18),
        ("warehouse", 16),
        ("data pipeline", 18),
        ("data sync", 18),
        ("schema", 10),
        ("lineage", 18),
        ("catalog", 14),
    ),
    "productivity": (
        ("productivity", 18),
        ("project management", 18),
        ("task management", 18),
        ("knowledge management", 14),
        ("notes", 10),
    ),
}

_AGENT_TAG_KEYWORDS: dict[str, tuple[tuple[str, int], ...]] = {
    "admin-panel": (("admin", 18), ("backoffice", 18), ("control panel", 16)),
    "approval": (("approval", 18), ("approve", 14), ("review queue", 12)),
    "analytics": (("analytics", 18), ("dashboard", 16), ("reporting", 16), ("insight", 12)),
    "api": (("api", 18), ("rest api", 18), ("graphql", 16), ("webhook", 16)),
    "auth": (("auth", 12), ("oauth", 18), ("sso", 18), ("rbac", 16), ("login", 10)),
    "automation": (("automation", 18), ("automate", 16), ("scheduled", 8)),
    "b2b": (("enterprise", 18), ("team", 12), ("teams", 12), ("workspace", 12), ("organization", 12), ("customer", 10)),
    "billing": (("billing", 18), ("pricing", 16), ("subscription", 16), ("invoice", 14)),
    "communication": (("chat", 18), ("email", 18), ("message", 14), ("messages", 14), ("messaging", 18)),
    "crm": (("crm", 20), ("sales", 16), ("lead", 16), ("pipeline", 10)),
    "data": (("etl", 18), ("warehouse", 16), ("catalog", 12), ("data pipeline", 18)),
    "database": (("database", 16), ("postgres", 16), ("mysql", 14), ("sqlite", 12)),
    "developer": (("developer", 14), ("sdk", 16), ("cli", 16), ("tooling", 14), ("framework", 10)),
    "devops": (("devops", 18), ("ci/cd", 18), ("deployment", 14), ("deploy", 10), ("terraform", 16), ("helm", 12)),
    "docker": (("docker", 18), ("dockerfile", 18), ("docker compose", 16), ("docker-compose", 16)),
    "embedded": (("embedded", 18), ("widget", 18), ("sdk", 10)),
    "enterprise": (("enterprise", 20), ("compliance", 12), ("sso", 12)),
    "forms": (("form", 16), ("forms", 16), ("form builder", 18), ("survey", 12)),
    "gateway": (("gateway", 18), ("proxy", 16), ("reverse proxy", 18)),
    "integrations": (("integration", 16), ("integrations", 16), ("connector", 14), ("connectors", 14), ("webhook", 10)),
    "kubernetes": (("kubernetes", 18), ("k8s", 18)),
    "lineage": (("lineage", 20),),
    "low-code": (("low-code", 18), ("low code", 18), ("no-code", 18), ("no code", 18)),
    "marketplace": (("marketplace", 18),),
    "migration": (("migration", 18), ("schema migration", 18), ("data migration", 18), ("sync", 10)),
    "monitoring": (("observability", 18), ("monitoring", 18), ("tracing", 16), ("logging", 14), ("metrics", 14), ("telemetry", 14)),
    "multi-tenant": (("multi-tenant", 18), ("multitenant", 18), ("tenant", 10)),
    "notifications": (("notification", 18), ("notifications", 18), ("alert", 12), ("alerts", 12)),
    "open-core-candidate": (("enterprise edition", 18), ("commercial", 10)),
    "platform": (("platform", 18),),
    "plugin-ecosystem": (("plugin", 18), ("plugins", 18), ("extension", 16), ("extensions", 16)),
    "postgres": (("postgres", 20), ("postgresql", 20)),
    "python": (("python", 18), ("fastapi", 12), ("django", 12), ("flask", 12)),
    "react": (("react", 18),),
    "reporting": (("reporting", 18), ("report", 12), ("reports", 12)),
    "self-hosted": (("self-hosted", 18), ("self hosted", 18), ("on-prem", 16), ("on prem", 16)),
    "smb": (("small business", 18), ("smb", 18)),
    "support": (("support", 12), ("helpdesk", 18), ("knowledge base", 16)),
    "ticketing": (("ticket", 18), ("tickets", 18), ("helpdesk", 12)),
    "typescript": (("typescript", 18),),
    "workflow": (("workflow", 18), ("workflows", 18), ("orchestrat*", 18), ("approval", 10)),
}

_NEW_TAG_SUGGESTION_KEYWORDS: dict[str, tuple[tuple[str, int], ...]] = {
    "benchmark": (("benchmark", 18), ("leaderboard", 14)),
    "browser-automation": (("browser automation", 20), ("playwright", 16), ("selenium", 16), ("chrome devtools", 14)),
    "mcp": (("mcp", 18), ("model context protocol", 20)),
    "research": (("paper", 14), ("dataset", 14), ("benchmark", 12)),
    "robotics": (("robot", 16), ("robotics", 18)),
    "template": (("template", 18), ("starter", 16), ("boilerplate", 16)),
    "theme": (("theme", 18), ("color scheme", 14)),
}

_STACK_AGENT_TAGS = frozenset(
    {
        "database",
        "docker",
        "go",
        "kubernetes",
        "nextjs",
        "postgres",
        "python",
        "react",
        "typescript",
    }
)

_HIGH_MONETIZATION_SIGNALS = (
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

_MEDIUM_MONETIZATION_SIGNALS = (
    "team",
    "teams",
    "workflow",
    "automation",
    "dashboard",
    "analytics",
    "platform",
    "api",
)


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


@lru_cache(maxsize=512)
def _signal_regex(pattern: str) -> re.Pattern[str]:
    normalized = pattern.strip().lower()
    if not normalized:
        return re.compile(r"$^")

    stem_match = normalized.endswith("*")
    if stem_match:
        normalized = normalized[:-1]

    escaped = re.escape(normalized).replace(r"\ ", r"[\s_\-]+")
    if stem_match:
        expression = rf"(?<![a-z0-9]){escaped}[a-z0-9_\-]*"
    else:
        expression = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return re.compile(expression)


def contains_signal(corpus: str, pattern: str) -> bool:
    return bool(_signal_regex(pattern).search(corpus))


def contains_any_signals(corpus: str, patterns: tuple[str, ...]) -> bool:
    return any(contains_signal(corpus, pattern) for pattern in patterns)


def _parse_heuristic_evidence(evidence: dict[str, object] | None) -> HeuristicEvidenceSnapshot:
    evidence = evidence or {}
    signals = evidence.get("signals")
    score_breakdown = evidence.get("score_breakdown")
    normalized_scores: dict[str, int] = {}
    if isinstance(score_breakdown, dict):
        normalized_scores = {
            str(key): int(value)
            for key, value in score_breakdown.items()
            if isinstance(key, str) and isinstance(value, (int, float))
        }
    return HeuristicEvidenceSnapshot(
        summary=_normalize_text(evidence.get("evidence_summary")) or "",
        signals=dict(signals) if isinstance(signals, dict) else {},
        score_breakdown=normalized_scores,
        supporting_signals=_normalize_text_list(evidence.get("supporting_signals")),
        red_flags=_normalize_text_list(evidence.get("red_flags")),
        contradictions=_normalize_text_list(evidence.get("contradictions")),
        missing_information=_normalize_text_list(evidence.get("missing_information")),
        insufficient_reason=_normalize_text(evidence.get("insufficient_evidence_reason")),
        analysis_mode_target=_normalize_text(evidence.get("analysis_mode_target")),
    )


def _build_search_text(
    *,
    repository_full_name: str,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> str:
    parts = [repository_full_name.lower(), lower_text, evidence.summary.lower()]
    topics = evidence.signals.get("topics")
    if isinstance(topics, list):
        parts.extend(str(topic).lower() for topic in topics if isinstance(topic, str))
    frameworks = evidence.signals.get("framework_signals")
    if isinstance(frameworks, list):
        parts.extend(str(item).lower() for item in frameworks if isinstance(item, str))
    languages = evidence.signals.get("primary_languages")
    if isinstance(languages, list):
        parts.extend(str(item).lower() for item in languages if isinstance(item, str))
    return "\n".join(part for part in parts if part)


def _score_weighted_keyword_hits(
    corpus: str,
    weighted_patterns: tuple[tuple[str, int], ...],
) -> int:
    return sum(weight for pattern, weight in weighted_patterns if contains_signal(corpus, pattern))


def _classify_category(
    *,
    repository_full_name: str,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> tuple[str | None, int]:
    search_text = _build_search_text(
        repository_full_name=repository_full_name,
        lower_text=lower_text,
        evidence=evidence,
    )
    signals = evidence.signals
    scores = {
        category: _score_weighted_keyword_hits(search_text, keywords)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }

    if bool(signals.get("has_api_surface")):
        scores["devtools"] += 6 if contains_any_signals(search_text, ("sdk", "cli", "plugin", "framework")) else 2
        scores["data"] += 6 if contains_any_signals(search_text, ("etl", "warehouse", "catalog", "lineage")) else 0
    if bool(signals.get("has_auth_signals")):
        scores["security"] += 12
    if bool(signals.get("has_frontend_surface")) and bool(signals.get("has_backend_surface")):
        scores["workflow"] += 8
        scores["analytics"] += 4 if contains_any_signals(search_text, ("dashboard", "reporting")) else 0
    if bool(signals.get("has_containerization")):
        scores["devops"] += 8
        scores["infrastructure"] += 6
    if bool(signals.get("readme_mentions_enterprise")):
        scores["security"] += 5
        scores["crm"] += 4
    if bool(signals.get("readme_mentions_api")) and contains_any_signals(search_text, ("platform", "gateway", "proxy")):
        scores["infrastructure"] += 8
    if contains_any_signals(search_text, ("template", "theme", "dotfiles", "config", "color scheme")):
        for category in ("workflow", "communication", "ai_ml", "analytics"):
            scores[category] = max(scores[category] - 8, 0)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_category, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < 12:
        return None, 0

    category_confidence = 30 + min(best_score, 40) + min(max(best_score - second_score, 0), 20)
    if evidence.insufficient_reason:
        category_confidence -= 20
    category_confidence -= min(len(evidence.contradictions) * 8, 16)
    if int(signals.get("readme_length", 0) or 0) < 120:
        category_confidence -= 8
    return best_category, max(0, min(category_confidence, 95))


def _extract_agent_tags(
    *,
    repository_full_name: str,
    lower_text: str,
    category: str | None,
    evidence: HeuristicEvidenceSnapshot,
) -> list[str]:
    search_text = _build_search_text(
        repository_full_name=repository_full_name,
        lower_text=lower_text,
        evidence=evidence,
    )
    signals = evidence.signals
    score_breakdown = evidence.score_breakdown
    tag_scores = {tag: 0 for tag in CONTROLLED_AGENT_TAGS}
    tag_scores.update({
        tag: _score_weighted_keyword_hits(search_text, keywords)
        for tag, keywords in _AGENT_TAG_KEYWORDS.items()
    })

    if category == "workflow":
        tag_scores["workflow"] += 18
        tag_scores["automation"] += 10
    elif category == "analytics":
        tag_scores["analytics"] += 18
        tag_scores["reporting"] += 10
    elif category == "devops":
        tag_scores["devops"] += 18
        tag_scores["docker"] += 8
    elif category == "infrastructure":
        tag_scores["gateway"] += 12
        tag_scores["platform"] += 10
    elif category == "devtools":
        tag_scores["developer"] += 18
    elif category == "crm":
        tag_scores["crm"] += 18
        tag_scores["b2b"] += 10
    elif category == "communication":
        tag_scores["communication"] += 18
        tag_scores["notifications"] += 10
    elif category == "support":
        tag_scores["support"] += 18
        tag_scores["ticketing"] += 10
    elif category == "observability":
        tag_scores["monitoring"] += 18
    elif category == "low_code":
        tag_scores["low-code"] += 18
        tag_scores["forms"] += 10
    elif category == "security":
        tag_scores["auth"] += 18
        tag_scores["enterprise"] += 8
    elif category == "ai_ml":
        tag_scores["saas-candidate"] += 4
    elif category == "data":
        tag_scores["data"] += 18
        tag_scores["lineage"] += 8

    if bool(signals.get("has_api_surface")):
        tag_scores["api"] += 18
    if bool(signals.get("has_auth_signals")):
        tag_scores["auth"] += 18
    if bool(signals.get("has_admin_surface")):
        tag_scores["admin-panel"] += 18
    if bool(signals.get("has_containerization")):
        tag_scores["docker"] += 12
    if bool(signals.get("has_deploy_config")):
        tag_scores["devops"] += 10
    if bool(signals.get("readme_mentions_team")):
        tag_scores["b2b"] += 12
    if bool(signals.get("readme_mentions_enterprise")):
        tag_scores["enterprise"] += 16
        tag_scores["b2b"] += 10
    if bool(signals.get("readme_mentions_plugin")):
        tag_scores["plugin-ecosystem"] += 14
        tag_scores["integrations"] += 10
    if bool(signals.get("has_frontend_surface")) and bool(signals.get("has_backend_surface")):
        tag_scores["platform"] += 8
        tag_scores["saas-candidate"] += 14
    if score_breakdown.get("hosted_gap_score", 0) >= 60:
        tag_scores["hosted-gap"] += 26
        tag_scores["saas-candidate"] += 12
    if score_breakdown.get("commercial_readiness_score", 0) >= 60:
        tag_scores["commercial-ready"] += 28
    if score_breakdown.get("market_timing_score", 0) >= 60:
        tag_scores["needs-deep-analysis"] += 22
    if evidence.insufficient_reason or evidence.contradictions:
        tag_scores["low-confidence"] += 24
    if signals.get("maintainer_concentration_risk") == "high":
        tag_scores["maintainer-risk"] += 22

    for framework in _normalize_text_list(signals.get("framework_signals")):
        if framework in tag_scores:
            tag_scores[framework] += 14
    for language in _normalize_text_list(signals.get("primary_languages")):
        if language in tag_scores:
            tag_scores[language] += 12

    ranked = [(tag, score) for tag, score in sorted(tag_scores.items(), key=lambda item: (-item[1], item[0])) if score >= 14]
    strategic = [tag for tag, _ in ranked if tag not in _STACK_AGENT_TAGS]
    stack = [tag for tag, _ in ranked if tag in _STACK_AGENT_TAGS]

    selected = strategic[:8]
    if len(selected) < 8:
        selected.extend(stack[: max(0, min(2, 8 - len(selected)))])
    if len(selected) < 8:
        selected.extend(stack[2 : 2 + (8 - len(selected))])

    if not selected and category is not None:
        selected = [category] if category in CONTROLLED_AGENT_TAGS else []
    return _dedupe(selected)[:8]


def _suggest_new_tags(
    *,
    repository_full_name: str,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> list[str]:
    search_text = _build_search_text(
        repository_full_name=repository_full_name,
        lower_text=lower_text,
        evidence=evidence,
    )
    suggestions = [
        tag
        for tag, patterns in _NEW_TAG_SUGGESTION_KEYWORDS.items()
        if _score_weighted_keyword_hits(search_text, patterns) >= 16 and tag not in CONTROLLED_AGENT_TAGS
    ]
    return _dedupe(suggestions)[:4]


def _score_monetization(
    *,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> MonetizationPotential:
    search_text = _build_search_text(
        repository_full_name="",
        lower_text=lower_text,
        evidence=evidence,
    )
    high_count = sum(contains_signal(search_text, signal) for signal in _HIGH_MONETIZATION_SIGNALS)
    medium_count = sum(contains_signal(search_text, signal) for signal in _MEDIUM_MONETIZATION_SIGNALS)
    commercial_readiness = evidence.score_breakdown.get("commercial_readiness_score", 0)
    hosted_gap = evidence.score_breakdown.get("hosted_gap_score", 0)
    market_timing = evidence.score_breakdown.get("market_timing_score", 0)

    if commercial_readiness >= 60 and (hosted_gap >= 45 or market_timing >= 45):
        return MonetizationPotential.HIGH
    if high_count >= 2 or (high_count >= 1 and medium_count >= 2):
        return MonetizationPotential.HIGH
    if commercial_readiness >= 35 or market_timing >= 35 or high_count >= 1 or medium_count >= 2:
        return MonetizationPotential.MEDIUM
    return MonetizationPotential.LOW


def _build_positive_signals(
    *,
    repository_full_name: str,
    lower_text: str,
    category: str | None,
    evidence: HeuristicEvidenceSnapshot,
) -> list[str]:
    search_text = _build_search_text(
        repository_full_name=repository_full_name,
        lower_text=lower_text,
        evidence=evidence,
    )
    signals = list(evidence.supporting_signals)
    if contains_any_signals(search_text, ("api", "integration", "webhook")):
        signals.append("Repository exposes a clear API or integration surface.")
    if contains_any_signals(search_text, ("team", "teams", "workspace", "organization")):
        signals.append("Repository appears oriented toward repeatable team workflows.")
    if category == "devtools":
        signals.append("Repository looks like a developer-facing tool rather than a hobby-only project.")
    if evidence.score_breakdown.get("commercial_readiness_score", 0) >= 60:
        signals.append("Commercial-readiness signals are meaningfully above the current baseline.")
    if evidence.score_breakdown.get("hosted_gap_score", 0) >= 60:
        signals.append("The evidence suggests a credible hosted-gap or packaging opportunity.")
    return _dedupe(signals)[:4] or [f"{repository_full_name} has a focused README with a clear product narrative."]


def _build_risk_signals(
    *,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> list[str]:
    search_text = _build_search_text(
        repository_full_name="",
        lower_text=lower_text,
        evidence=evidence,
    )
    signals = list(evidence.red_flags)
    if not contains_any_signals(search_text, ("pricing", "paid", "subscription", "billing")):
        signals.append("Packaging and monetization details are still weak.")
    if not contains_any_signals(search_text, ("customer", "team", "user", "operator", "workspace")):
        signals.append("Target customer and operator are not clearly named.")
    if not contains_any_signals(search_text, ("security", "compliance", "oauth", "sso", "rbac")):
        signals.append("Trust and security positioning is still thin.")
    return _dedupe(signals)[:4] or ["README leaves important commercial detail unspecified."]


def _build_missing_feature_signals(
    *,
    lower_text: str,
    evidence: HeuristicEvidenceSnapshot,
) -> list[str]:
    search_text = _build_search_text(
        repository_full_name="",
        lower_text=lower_text,
        evidence=evidence,
    )
    signals = list(evidence.missing_information)
    if not contains_any_signals(search_text, ("pricing", "billing", "subscription")):
        signals.append("Missing pricing, billing, or packaging detail.")
    if not contains_any_signals(search_text, ("integration", "integrations", "api", "webhook")):
        signals.append("Missing ecosystem integrations or API extensibility signal.")
    if not contains_any_signals(search_text, ("team", "workspace", "collaboration", "organization")):
        signals.append("Missing collaboration or workspace workflow detail.")
    if not contains_any_signals(search_text, ("analytics", "report", "reporting", "dashboard")):
        signals.append("Missing analytics or reporting story.")
    return _dedupe(signals)[:4]


def _compute_confidence_score(
    *,
    readme: NormalizedReadme,
    category: str | None,
    category_confidence_score: int,
    agent_tags: list[str],
    evidence: HeuristicEvidenceSnapshot,
) -> int:
    score = 10
    if category is not None:
        score += category_confidence_score // 2
    if readme.normalized_character_count >= 600:
        score += 18
    elif readme.normalized_character_count >= 250:
        score += 12
    elif readme.normalized_character_count >= 120:
        score += 6
    if len(agent_tags) >= 4:
        score += 12
    elif len(agent_tags) >= 2:
        score += 8
    elif agent_tags:
        score += 4

    score += min(evidence.score_breakdown.get("technical_maturity_score", 0) // 10, 10)
    score += min(evidence.score_breakdown.get("commercial_readiness_score", 0) // 10, 10)
    if bool(evidence.signals.get("repository_description_present")):
        score += 4
    if evidence.analysis_mode_target == "deep":
        score += 4
    score -= min(len(evidence.contradictions) * 10, 20)
    score -= min(len(evidence.red_flags) * 4, 12)
    if evidence.insufficient_reason:
        score -= 30
    return max(0, min(score, 95))


def _infer_target_audience(*, agent_tags: list[str], category: str | None) -> str | None:
    if "developer" in agent_tags or category == "devtools":
        return "Developers and technical teams"
    if "b2b" in agent_tags:
        return "Business teams and operators"
    if category == "communication":
        return "Teams that coordinate messages, inboxes, or notifications"
    if category == "analytics":
        return "Operators who need dashboards, reporting, or insights"
    return None


def _infer_target_customer(
    *,
    agent_tags: list[str],
    evidence: HeuristicEvidenceSnapshot,
) -> str | None:
    if "enterprise" in agent_tags:
        return "Enterprise or security-conscious teams"
    if "b2b" in agent_tags:
        return "Internal business teams or SaaS operators"
    if "developer" in agent_tags:
        return "Developer teams"
    if evidence.insufficient_reason:
        return "Unclear from available evidence"
    return None


def _infer_product_type(*, category: str | None, agent_tags: list[str]) -> str | None:
    if category is None:
        return "Open-source software project"
    if category == "devtools":
        return "Developer tool or framework"
    if category == "analytics":
        return "Analytics or reporting product"
    if category == "workflow":
        return "Workflow automation product"
    if "gateway" in agent_tags:
        return "Gateway or infrastructure product"
    return category.replace("_", " ").title()


def _infer_business_model(
    *,
    monetization_potential: MonetizationPotential,
    agent_tags: list[str],
    evidence: HeuristicEvidenceSnapshot,
) -> str | None:
    if monetization_potential is MonetizationPotential.HIGH:
        if "self-hosted" in agent_tags or evidence.score_breakdown.get("hosted_gap_score", 0) >= 60:
            return "Likely hosted SaaS or managed-service opportunity on top of OSS functionality"
        return "Likely B2B SaaS or paid team plan"
    if monetization_potential is MonetizationPotential.MEDIUM:
        return "Possible team subscription, hosted packaging, or open-core upsell"
    return "Open-source utility with unclear direct monetization path"


def _infer_technical_stack(evidence: HeuristicEvidenceSnapshot) -> str | None:
    components = [
        *[item.title() for item in _normalize_text_list(evidence.signals.get("primary_languages"))],
        *[item.title() for item in _normalize_text_list(evidence.signals.get("framework_signals"))],
    ]
    normalized = _dedupe([component for component in components if component])
    return ", ".join(normalized[:5]) if normalized else None


def _recommend_action(
    *,
    confidence_score: int,
    monetization_potential: MonetizationPotential,
    agent_tags: list[str],
    evidence: HeuristicEvidenceSnapshot,
) -> str | None:
    if evidence.insufficient_reason:
        return "Needs manual review or richer repository evidence before shortlisting."
    if confidence_score >= 75 and monetization_potential is MonetizationPotential.HIGH:
        return "Shortlist for operator review and compare hosted competitors or pricing gaps."
    if "hosted-gap" in agent_tags:
        return "Review as a hosted-gap candidate and inspect pricing, auth, and deployment packaging."
    if confidence_score < 55:
        return "Keep in backlog and rerun with richer evidence or LLM analysis before favoriting."
    return "Keep monitored and review alongside similar repositories in the same cluster."


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = re.sub(r"\s+", " ", value).strip()
    return candidate or None


def _normalize_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        candidate = _normalize_text(item)
        if candidate:
            normalized.append(candidate)
    return normalized


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
