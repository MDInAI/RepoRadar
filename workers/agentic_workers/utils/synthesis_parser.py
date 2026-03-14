"""Parse structured data from synthesis LLM output."""
import re


def parse_synthesis_output(output_text: str) -> dict[str, object]:
    """Extract title, summary, and key insights from synthesis output.

    Returns dict with keys: title, summary, key_insights
    """
    if not output_text or not output_text.strip():
        return {"title": None, "summary": None, "key_insights": None}

    lines = output_text.strip().split("\n")
    title = None
    summary = None
    insights = []

    # Extract title (first non-empty line or heading)
    for line in lines:
        line = line.strip()
        if line:
            title = re.sub(r"^#+\s*", "", line)  # Remove markdown heading
            break

    # Extract summary (first paragraph after title)
    in_paragraph = False
    summary_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            if in_paragraph:
                break
            continue
        if not stripped.startswith("#") and not stripped.startswith("-") and not stripped.startswith("*"):
            in_paragraph = True
            summary_lines.append(stripped)

    if summary_lines:
        summary = " ".join(summary_lines)[:1000]  # Limit length

    # Extract insights (bullet points and numbered lists)
    for line in lines:
        stripped = line.strip()
        # Match bullet points (- or *)
        if stripped.startswith("-") or stripped.startswith("*"):
            insight = re.sub(r"^[-*]\s*", "", stripped)
            if insight:
                insights.append(insight)
        # Match numbered lists (1. 2. 3. etc.)
        elif re.match(r"^\d+\.\s+", stripped):
            insight = re.sub(r"^\d+\.\s+", "", stripped)
            if insight:
                insights.append(insight)

    return {
        "title": title[:500] if title else None,
        "summary": summary,
        "key_insights": insights[:10] if insights else None,
    }
