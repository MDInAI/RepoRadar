# Agentic-Workflow

A local-first orchestration and operator dashboard for intelligent repository discovery, analysis, and idea synthesis. Built as a separate localhost application connected to OpenClaw, this project serves as a complete **Opportunity Engine** for the GitHub ecosystem.

## 🌟 Core Features

### 🧠 Multi-Agent Orchestration Pipeline
The core system is powered by 7 specialized agents working in sequence to find, filter, analyze, and synthesize repositories:

- **🔥 Firehose**: Continuously polls GitHub's search API to discover new and trending repositories in real-time, respecting pagination and rate limits.
- **🕰️ Backfill**: Discovers older repositories by working backwards through sliding time windows, ensuring historical coverage gaps are comprehensively filled.
- **🛡️ Bouncer**: A deterministic rule-based engine that filters incoming repositories using strict include/exclude regex patterns, saving expensive compute.
- **🔎 Analyst**: Fetches READMEs, extracts deterministic evidence (manifests, metadata, file trees), and produces evidence-backed business analysis using **Fast** (heuristic/deterministic) and **Deep** (LLM-backed) reasoning paths.
- **🧬 Combiner**: An LLM-powered agent that synthesizes insights from multiple repositories to propose composite business opportunities and merged product architectures.
- **🔄 Obsession**: Long-lived context tracking for synthesis work. It maintains "obsession contexts" to incrementally refine ideas and memory segments across multiple agent runs.
- **👑 Overlord**: The control-plane coordinator that manages pacing, fault detection, and exact pipeline resumption.

### 💡 Opportunity Engine & Synthesis
- **Idea Families**: Instead of treating every repository in isolation, the system clusters repositories that solve the same user problem (e.g., open-source CRMs, self-hosted form builders).
- **Opportunity Scoring**: Scores repository clusters based on Demand, Quality, Buildability, Whitespace (missing enterprise features/hosting), and Merge Potential.
- **Generative Synthesis**: Uses LLMs (like Anthropic Claude 3.5 Sonnet) to propose multi-repository "merged product" ideas, highlighting target users, moats, missing features, and monetization paths.

### 📊 Advanced Repository Intelligence
- **Taxonomy & Tagging**: Replaces naive categorization with a controlled vocabulary of primary business categories (e.g., `devops`, `crm`, `ai_ml`) and structured analyst tags (`b2b`, `hosted-gap`, `saas-candidate`, `commercial-ready`).
- **Evidence-Backed Analysis**: Analyzes technical maturity, commercial readiness, trust risk, and market timing based on actual repository artifacts (manifests, CI configs, releases) rather than just README keywords.
- **Contradiction Engine**: Detects tensions between a repository's README claims and its actual observed evidence.
- **Confidence Calibration**: Emits strict confidence scores on analysis outcomes to differentiate high-signal insights from low-confidence guesses.

### ⚙️ Robust Local Infrastructure
- **Rate-Limit Aware**: Agents share GitHub API tokens using smart pacing and automatic backoff/resume mechanics.
- **Failure & Pause Handling**: Sophisticated pause policies automatically suspend individual agents or groups on API rate limits or transient errors, preserving exact checkpoints.
- **Artifact-First Storage**: Produces raw JSON evidence artifacts and analysis payloads locally in `runtime/` without bloating the operational SQLite database.

---

## Project Structure

```text
agentic-workflow/
├── frontend/    # Next.js App Router dashboard (agentic-workflow-ui)
├── backend/     # FastAPI control-plane API
├── workers/     # Python worker/scheduler processes
├── docs/        # Project architecture and master plans
├── scripts/     # Development & operational scripts
└── runtime/     # Generated data, logs, readmes, and temp files (gitignored)
```

## Runtime Topology

Three local service areas run independently:

1. **Dashboard Frontend** — Next.js dev server (`frontend/`) on Port 3000
2. **Control API** — FastAPI/Uvicorn (`backend/`) on Port 8000
3. **Worker Processes** — Python schedulers and jobs (`workers/`) running in the background

The MVP targets multi-agent operation from the start.

## Quick Start

```bash
# Bootstrap all services (installs dependencies)
./scripts/bootstrap.sh

# Start all services for local development
./scripts/dev.sh

# Run database migrations (backend)
./scripts/migrate.sh
```

## Gateway Integration Contract

The control-plane integration boundary is `frontend -> Agentic-Workflow backend -> Gateway`. See `docs/gateway-integration-contract.md` for the canonical contract introduced in Story 1.2 and extended for explicit multi-agent runtime assumptions in Story 1.3. 

Story 1.4 adds `docs/configuration-ownership.md` as the canonical source for local configuration ownership and validation rules:
- OpenClaw owns `~/.openclaw/openclaw.json`, including Gateway auth and default model conventions.
- Agentic-Workflow owns local runtime paths, provider credentials (`GITHUB_PROVIDER_TOKEN`, `ANTHROPIC_API_KEY`), and pacing/rate-limit thresholds in project env files.

## Out of Scope

The following existing OpenClaw-native paths are **not** part of this project and must not be modified:

- `dashboard/` — OpenClaw native dashboard
- `agents/` — OpenClaw agent definitions
- `workspace/mission-control/` — Separate workspace project
- Top-level Gateway/runtime files

## Security Model

Localhost-only single-operator MVP. No authentication or RBAC in this phase.

## Architecture & Documentation

See the `docs/` directory for detailed architecture documentation, including the `AGENT_ARCHITECTURE.md`, `opportunity-engine-proposal.md`, and `analyst-enhancement-master-plan.md`.

For the current Analyst implementation and website testing flow, see `docs/analyst-enhancement-testing-guide.md`.
