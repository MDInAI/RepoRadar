"""Convert user-provided idea text or repo URLs into GitHub search queries."""

from __future__ import annotations

import re


def generate_search_queries(idea_text: str) -> list[str]:
    """Generate 1-3 GitHub search query strings from a free-text idea description.

    Each returned query is the ``q=`` value for the GitHub Search API, without
    any ``created:`` date range qualifiers (those are appended by the job
    based on checkpoint state).
    """
    if not idea_text or not idea_text.strip():
        raise ValueError("idea_text must be non-empty")

    cleaned = idea_text.strip()
    queries: list[str] = []

    # Strategy 1: Exact phrase match on the full idea
    phrase = _normalise_phrase(cleaned)
    if phrase:
        queries.append(f'"{phrase}" archived:false is:public')

    # Strategy 2: Hyphenated variant (common in repo names)
    hyphenated = _hyphenate(cleaned)
    if hyphenated and hyphenated != phrase:
        queries.append(f'"{hyphenated}" archived:false is:public')

    # Strategy 3: Individual keyword OR query (if >= 3 words)
    keywords = _extract_keywords(cleaned)
    if len(keywords) >= 2:
        or_clause = " OR ".join(keywords[:5])
        queries.append(f"{or_clause} archived:false is:public")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

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
    """Convert 'trading bot' → 'trading-bot'."""
    normalised = _normalise_phrase(text)
    return normalised.replace(" ", "-")


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords, removing stopwords."""
    words = _normalise_phrase(text).split()
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2]
