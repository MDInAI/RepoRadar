"""Convert user-provided idea text or repo URLs into GitHub search queries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


_QUERY_BUILDER_SYSTEM_PROMPT = """You generate GitHub repository search queries.

Return JSON only with this schema:
{"queries": ["query one", "query two", "query three"]}

Rules:
- Return 1 to 3 queries.
- Each query must be suitable for the GitHub Search API q parameter.
- Do not include created:, pushed:, or sort qualifiers.
- Do not include q=.
- Keep queries concise and discovery-oriented.
- Favor exact phrases, repo-name variants, and crisp keyword combinations.
- Include archived:false and is:public in every query.
"""


def generate_search_queries(idea_text: str) -> list[str]:
    """Generate 1-3 GitHub search query strings from a free-text idea description.

    Each returned query is the ``q=`` value for the GitHub Search API, without
    any ``created:`` date range qualifiers (those are appended by the job
    based on checkpoint state).

    The three strategies target different dimensions of the search space:
    1. Repository name/topic matching (how repos are named)
    2. Description/README matching (how repos describe themselves)
    3. Keyword combination matching (broader topical discovery)
    """
    if not idea_text or not idea_text.strip():
        raise ValueError("idea_text must be non-empty")

    cleaned = idea_text.strip()
    queries: list[str] = []
    keywords = _extract_keywords(cleaned)
    hyphenated = _hyphenate(cleaned)

    # Strategy 1: Match repo names — repos are commonly named with hyphens
    if hyphenated:
        queries.append(f"{hyphenated} in:name archived:false is:public")

    # Strategy 2: Match descriptions — find repos that describe what we're looking for
    phrase = _normalise_phrase(cleaned)
    if phrase:
        queries.append(f'"{phrase}" in:description,readme archived:false is:public')

    # Strategy 3: Keyword combination with topic qualifiers
    if len(keywords) >= 2:
        # Use top 3 keywords as AND (implicit), more precise than OR
        kw_slice = keywords[:3]
        queries.append(f"{' '.join(kw_slice)} archived:false is:public")

    return _dedupe_queries(queries)


def generate_search_queries_using_analyst_settings(idea_text: str) -> dict[str, Any]:
    from agentic_workers.core.config import settings

    provider = settings.ANALYST_PROVIDER
    if provider == "llm":
        queries = _generate_search_queries_with_anthropic(
            idea_text,
            api_key=settings.ANTHROPIC_API_KEY.get_secret_value() if settings.ANTHROPIC_API_KEY else None,
            model_name=settings.ANALYST_MODEL_NAME,
        )
        return {
            "queries": queries,
            "provider": "anthropic",
            "model": settings.ANALYST_MODEL_NAME,
        }
    if provider == "gemini":
        queries = _generate_search_queries_with_gemini(
            idea_text,
            api_key=settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None,
            api_keys=settings.gemini_api_key_values,
            base_url=settings.GEMINI_BASE_URL,
            model_name=settings.GEMINI_MODEL_NAME,
        )
        return {
            "queries": queries,
            "provider": "gemini-compatible",
            "model": settings.GEMINI_MODEL_NAME,
        }

    return {
        "queries": generate_search_queries(idea_text),
        "provider": "heuristic",
        "model": None,
    }


def _generate_search_queries_with_anthropic(
    idea_text: str,
    *,
    api_key: str | None,
    model_name: str | None,
) -> list[str]:
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required when ANALYST_PROVIDER=llm")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_name or "claude-3-5-haiku-20241022",
        max_tokens=400,
        timeout=30.0,
        system=_QUERY_BUILDER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_query_prompt(idea_text)}],
    )

    text_parts = [
        block.text
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    return _parse_llm_query_payload("\n".join(text_parts))


def _generate_search_queries_with_gemini(
    idea_text: str,
    *,
    api_key: str | None,
    api_keys: tuple[str, ...] | list[str] | None,
    base_url: str | None,
    model_name: str | None,
) -> list[str]:
    configured_keys = [
        *(api_keys or ()),
        *([api_key] if isinstance(api_key, str) and api_key.strip() else []),
    ]
    usable_keys = [str(key).strip() for key in configured_keys if str(key).strip()]
    if not usable_keys:
        raise ValueError("GEMINI_API_KEY or GEMINI_API_KEYS is required when ANALYST_PROVIDER=gemini")

    from openai import OpenAI

    client = OpenAI(
        api_key=usable_keys[0],
        base_url=base_url or "https://api.haimaker.ai/v1",
    )
    response = client.chat.completions.create(
        model=model_name or "google/gemini-2.0-flash-001",
        messages=[
            {"role": "system", "content": _QUERY_BUILDER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_query_prompt(idea_text)},
        ],
        max_tokens=400,
        timeout=30.0,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty response from Gemini query builder")
    return _parse_llm_query_payload(content)


def _build_query_prompt(idea_text: str) -> str:
    return f"""Product thesis:
{idea_text.strip()}

Generate GitHub search queries that would help discover public repositories aligned to this thesis.
Return only JSON with a top-level "queries" array.
"""


def _parse_llm_query_payload(raw_text: str) -> list[str]:
    cleaned = _strip_code_fences(raw_text).strip()
    if not cleaned:
        raise ValueError("Empty response from LLM query builder")

    payload = json.loads(cleaned)
    if isinstance(payload, dict):
        raw_queries = payload.get("queries")
    elif isinstance(payload, list):
        raw_queries = payload
    else:
        raw_queries = None

    if not isinstance(raw_queries, list):
        raise ValueError("LLM query builder response must contain a queries array")

    queries = [_normalise_generated_query(str(query)) for query in raw_queries if str(query).strip()]
    queries = [query for query in queries if query]
    if not queries:
        raise ValueError("LLM query builder did not return any usable queries")
    return _dedupe_queries(queries)


def _normalise_generated_query(query: str) -> str:
    normalized = query.strip()
    normalized = re.sub(r"^q=", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\b(created|pushed|updated|sort):\S+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""
    if "archived:false" not in normalized:
        normalized = f"{normalized} archived:false"
    if "is:public" not in normalized:
        normalized = f"{normalized} is:public"
    return re.sub(r"\s+", " ", normalized).strip()


def _strip_code_fences(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```json"):
        candidate = candidate[7:]
    elif candidate.startswith("```"):
        candidate = candidate[3:]
    if candidate.endswith("```"):
        candidate = candidate[:-3]
    return candidate.strip()


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        if query and query not in seen:
            seen.add(query)
            unique.append(query)
    return unique[:3]


def generate_queries_from_repo_metadata(
    *,
    description: str | None = None,
    topics: list[str] | None = None,
    language: str | None = None,
) -> list[str]:
    """Generate search queries from repository metadata."""
    queries: list[str] = []
    parts: list[str] = []

    if topics:
        topic_query = " ".join(f"topic:{t}" for t in topics[:3])
        parts.append(topic_query)
        queries.append(f"{topic_query} archived:false is:public")

    if description:
        phrase = _normalise_phrase(description)
        if phrase and len(phrase) <= 100:
            lang_qual = f" language:{language}" if language else ""
            queries.append(f'"{phrase}"{lang_qual} archived:false is:public')

    if language and not parts:
        keywords = _extract_keywords(description or "")
        if keywords:
            kw_clause = " ".join(keywords[:3])
            queries.append(f"{kw_clause} language:{language} archived:false is:public")

    return queries[:3]


# --- internal helpers ---

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "to", "was", "were", "with", "open", "source", "free",
})


def _normalise_phrase(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _hyphenate(text: str) -> str:
    """Convert 'trading bot' -> 'trading-bot'."""
    normalised = _normalise_phrase(text)
    return normalised.replace(" ", "-")


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords, removing stopwords."""
    words = _normalise_phrase(text).split()
    return [word for word in words if word not in _STOPWORDS and len(word) >= 2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Scout search queries.")
    parser.add_argument("--idea-text", required=True, help="Idea or thesis to convert into GitHub queries.")
    args = parser.parse_args(argv)

    try:
        payload = generate_search_queries_using_analyst_settings(args.idea_text)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
