from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    agent_name: str
    display_name: str
    role_label: str
    description: str
    implementation_status: str
    runtime_kind: str
    uses_github_token: bool
    uses_model: bool
    configured_provider: str | None
    configured_model: str | None
    notes: tuple[str, ...]


def get_agent_metadata(agent_name: str) -> AgentMetadata:
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    catalog: dict[str, AgentMetadata] = {
        "overlord": AgentMetadata(
            agent_name="overlord",
            display_name="Overlord",
            role_label="Control-plane coordinator",
            description="Dashboard-visible control-plane placeholder; no dedicated workflow worker is running yet.",
            implementation_status="placeholder",
            runtime_kind="control-plane-placeholder",
            uses_github_token=False,
            uses_model=False,
            configured_provider=None,
            configured_model=None,
            notes=(
                "Shown in the roster, but no standalone worker loop currently executes Overlord jobs.",
                "No model or token usage is tracked for this agent today.",
            ),
        ),
        "firehose": AgentMetadata(
            agent_name="firehose",
            display_name="Firehose",
            role_label="Repository intake",
            description="Discovers repositories from GitHub new and trending feeds.",
            implementation_status="live",
            runtime_kind="github-api-worker",
            uses_github_token=True,
            uses_model=False,
            configured_provider="github",
            configured_model=None,
            notes=(
                "Uses GITHUB_PROVIDER_TOKEN for GitHub API requests.",
                "Does not call an LLM model.",
            ),
        ),
        "backfill": AgentMetadata(
            agent_name="backfill",
            display_name="Backfill",
            role_label="Historical intake",
            description="Replays older GitHub repository windows to fill historical coverage.",
            implementation_status="live",
            runtime_kind="github-api-worker",
            uses_github_token=True,
            uses_model=False,
            configured_provider="github",
            configured_model=None,
            notes=(
                "Uses GITHUB_PROVIDER_TOKEN for GitHub API requests.",
                "Does not call an LLM model.",
            ),
        ),
        "bouncer": AgentMetadata(
            agent_name="bouncer",
            display_name="Bouncer",
            role_label="Rule-based triage",
            description="Applies local include and exclude rules to intake candidates.",
            implementation_status="live",
            runtime_kind="rules-engine",
            uses_github_token=False,
            uses_model=False,
            configured_provider="local-rules",
            configured_model=None,
            notes=(
                "Runs entirely in-process with deterministic rules.",
                "Does not call GitHub or an LLM model during triage.",
            ),
        ),
        "analyst": AgentMetadata(
            agent_name="analyst",
            display_name="Analyst",
            role_label="README analysis",
            description="Fetches READMEs from GitHub and scores monetization heuristically.",
            implementation_status="live",
            runtime_kind="heuristic-analysis",
            uses_github_token=True,
            uses_model=False,
            configured_provider="heuristic-readme-analysis",
            configured_model=None,
            notes=(
                "Fetches README content through the GitHub provider.",
                "Current implementation uses HeuristicReadmeAnalysisProvider, not an LLM.",
            ),
        ),
        "combiner": AgentMetadata(
            agent_name="combiner",
            display_name="Combiner",
            role_label="Opportunity synthesis",
            description="Synthesizes multi-repository opportunities from README inputs and prior insights.",
            implementation_status="live",
            runtime_kind="llm-synthesis" if has_anthropic else "heuristic-synthesis",
            uses_github_token=False,
            uses_model=has_anthropic,
            configured_provider="anthropic" if has_anthropic else "heuristic-combiner",
            configured_model="claude-3-5-sonnet-20241022" if has_anthropic else None,
            notes=(
                "Uses Anthropic when ANTHROPIC_API_KEY is configured.",
                "Falls back to a local heuristic synthesizer when the Anthropic key is unavailable.",
            ),
        ),
        "obsession": AgentMetadata(
            agent_name="obsession",
            display_name="Obsession",
            role_label="Context tracking",
            description="Tracks obsession contexts, memory segments, and refresh triggers.",
            implementation_status="partial",
            runtime_kind="workflow-state",
            uses_github_token=False,
            uses_model=False,
            configured_provider="workflow-state",
            configured_model=None,
            notes=(
                "Stores workflow state and triggers synthesis work, but no standalone obsession worker loop runs yet.",
                "Any model usage currently happens through downstream synthesis jobs rather than directly here.",
            ),
        ),
    }

    try:
        return catalog[agent_name]
    except KeyError as exc:
        raise ValueError(f"Unknown agent metadata requested for '{agent_name}'.") from exc
