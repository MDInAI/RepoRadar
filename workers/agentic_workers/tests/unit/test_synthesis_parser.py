"""Tests for synthesis output parser."""
import pytest
from agentic_workers.utils.synthesis_parser import parse_synthesis_output


def test_parse_basic_output():
    output = """# Innovative AI Tools

This is a summary of the synthesis combining multiple repositories.

- Key insight one
- Key insight two
- Key insight three"""

    result = parse_synthesis_output(output)
    assert result["title"] == "Innovative AI Tools"
    assert "summary" in result["summary"]
    assert result["key_insights"] == [
        "Key insight one",
        "Key insight two",
        "Key insight three",
    ]


def test_parse_empty_output():
    result = parse_synthesis_output("")
    assert result["title"] is None
    assert result["summary"] is None
    assert result["key_insights"] is None


def test_parse_malformed_output():
    output = "Just some random text without structure"
    result = parse_synthesis_output(output)
    assert result["title"] == "Just some random text without structure"
    assert result["summary"] is None
    assert result["key_insights"] is None


def test_parse_with_markdown_heading():
    output = "## Title with Hashes\n\nSummary text here.\n\n- Insight"
    result = parse_synthesis_output(output)
    assert result["title"] == "Title with Hashes"
    assert "Summary" in result["summary"]


def test_parse_with_asterisk_bullets():
    output = "Title\n\n* First insight\n* Second insight"
    result = parse_synthesis_output(output)
    assert result["key_insights"] == ["First insight", "Second insight"]


def test_parse_truncates_long_title():
    long_title = "A" * 600
    output = f"{long_title}\n\nSummary"
    result = parse_synthesis_output(output)
    assert len(result["title"]) == 500


def test_parse_truncates_long_summary():
    long_summary = "B" * 2000
    output = f"Title\n\n{long_summary}"
    result = parse_synthesis_output(output)
    assert len(result["summary"]) == 1000


def test_parse_limits_insights():
    insights = "\n".join([f"- Insight {i}" for i in range(20)])
    output = f"Title\n\n{insights}"
    result = parse_synthesis_output(output)
    assert len(result["key_insights"]) == 10


def test_parse_numbered_list():
    output = """# AI Innovation Report

This synthesis combines insights from multiple repositories.

1. First key insight
2. Second key insight
3. Third key insight"""

    result = parse_synthesis_output(output)
    assert result["title"] == "AI Innovation Report"
    assert "synthesis" in result["summary"]
    assert result["key_insights"] == [
        "First key insight",
        "Second key insight",
        "Third key insight",
    ]
