# Agentic-Workflow

A local-first orchestration and operator dashboard for intelligent repository discovery, analysis, and idea synthesis. Built as a localhost application that connects to OpenClaw, this project serves as an **Opportunity Engine** for the GitHub ecosystem.

This repository is published as **`agentic-parser`** on GitHub; internal Python packages and UI names may still use `agentic-workflow-*` for historical continuity.

## Core Features

### 🧠 Multi-Agent Orchestration Pipeline
The core system is powered by specialized agents working in sequence to find, filter, analyze, and synthesize repositories:

- **🔥 Firehose**: Continuously polls GitHub's search API to discover new and trending repositories in real time, respecting pagination and rate limits.
- **🕰️ Backfill**: Discovers older repositories by working backwards through sliding time windows, filling historical coverage gaps.
- **🛡️ Bouncer**: A deterministic rule-based engine that filters incoming repositories using strict include/exclude patterns, saving expensive compute.
- **🔎 Analyst**: Fetches READMEs, extracts deterministic evidence (manifests, metadata, file trees), and produces evidence-backed business analysis using **Fast** (heuristic/deterministic) and **Deep** (LLM-backed) reasoning paths. Supports multiple analyst backends (see [Analyst configuration](#analyst-configuration)).
- **🧬 Combiner**: An LLM-powered agent that synthesizes insights from multiple repositories to propose composite business opportunities and merged product architectures, including **deep synthesis** runs for larger result sets.
- **🔄 Obsession**: Long-lived context tracking for synthesis work. It maintains "obsession contexts" to incrementally refine ideas and memory segments across multiple agent runs.
- **👑 Overlord**: The control-plane coordinator that manages pacing, fault detection, and exact pipeline resumption. The FastAPI backend runs an Overlord evaluation loop alongside the API.

### 💡 Opportunity Engine & Synthesis
- **Idea Families**: Clusters repositories that solve the same user problem (for example open-source CRMs or self-hosted form builders), with APIs to create families from **Idea Scout** search results.
- **Idea Scout**: Named discovery workflows (queries, progress, discovery results) that feed the catalog and idea families.
- **Opportunity Scoring**: Scores repository clusters using Demand, Quality, Buildability, Whitespace (missing enterprise features/hosting), and Merge Potential.
- **Generative Synthesis**: Uses LLMs (for example Anthropic Claude) to propose multi-repository "merged product" ideas, with target users, moats, missing features, and monetization paths.

### 📊 Advanced Repository Intelligence
- **Taxonomy & Tagging**: Controlled vocabulary of primary business categories (for example `devops`, `crm`, `ai_ml`) and structured analyst tags (`b2b`, `hosted-gap`, `saas-candidate`, `commercial-ready`).
- **Evidence-Backed Analysis**: Technical maturity, commercial readiness, trust risk, and market timing from repository artifacts (manifests, CI configs, releases), not only README keywords.
- **Contradiction Engine**: Surfaces tensions between README claims and observed evidence.
- **Confidence Calibration**: Strict confidence scores on analysis outcomes.

### ⚙️ Robust Local Infrastructure
- **Rate-Limit Aware**: Shared GitHub API tokens with pacing, optional multi-token rotation (`GITHUB_PROVIDER_TOKENS`), and backoff/resume behavior.
- **Failure & Pause Handling**: Pause policies suspend agents or groups on rate limits or transient errors, preserving checkpoints.
- **Artifact-First Storage**: Raw JSON evidence and analysis payloads under `runtime/` (gitignored) so the operational SQLite database stays lean.
- **SSE & Events**: Server-sent events bridge persisted system events to the dashboard for live monitoring.
- **Retention**: Periodic cleanup of old operational history (system events, agent runs) to keep the database bounded.

---

## Tech Stack

| Area | Stack |
|------|--------|
| Backend | Python 3.11+, FastAPI, SQLModel, Alembic, Uvicorn, `sse-starlette` |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS |
| Workers | Python package `agentic_workers`, same DB/runtime as the API |
| Tooling | [uv](https://github.com/astral-sh/uv) for Python dependency install and scripts |

---

## Project Structure

```text
agentic-parser/
├── frontend/        # Next.js dashboard (package: agentic-workflow-ui)
├── backend/         # FastAPI control-plane API (package: agentic-workflow-api)
├── workers/         # Background worker processes (package: agentic-workers)
├── docs/            # Architecture, contracts, and planning docs
├── deployment/      # Operator guides, API reference, deployment checklist
├── scripts/         # bootstrap.sh, dev.sh, migrate.sh (bash)
├── runtime/         # Generated data, DB, logs, locks (gitignored — create via usage)
└── PLAN-deep-synthesis.md   # Roadmap/plan for deep synthesis pipeline features
```

## Runtime Topology

Three local service areas run together for full development:

1. **Dashboard** — Next.js (`frontend/`), default port **3000**
2. **Control API** — FastAPI/Uvicorn (`backend/`), default port **8000** (OpenAPI UI: `/docs`)
3. **Workers** — `python -m agentic_workers.main` (`workers/`), background schedulers and jobs

`scripts/dev.sh` starts the frontend and backend, runs migrations, and starts workers unless a worker lock indicates an existing process is already running.

## Dashboard (main routes)

| Route | Purpose |
|-------|---------|
| `/` | Home |
| `/overview` | High-level overview |
| `/agents` | Agent status, pacing, GitHub budget, Gemini key pool (where configured) |
| `/live` | Live event stream |
| `/scout` | Idea Scout searches and discovery |
| `/repositories` | Repository catalog and detail |
| `/ideas` | Idea families and synthesis |
| `/taxonomy` | Taxonomy and tagging |
| `/settings` | Settings |
| `/incidents` | Incidents |
| `/control` | Control panel |

## Prerequisites

- **Node.js** and npm (for the frontend)
- **uv** (for backend and workers; `bootstrap.sh` exits if `uv` is missing)
- **Bash** for `scripts/*.sh` (on Windows, use Git Bash, MSYS2, or WSL)

## Quick Start

```bash
# Copy environment templates (root drives dev.sh; backend/workers have their own .env.example)
cp .env.example .env
# Edit .env: DATABASE_URL, AGENTIC_RUNTIME_DIR, OPENCLAW_* paths, GITHUB_PROVIDER_TOKEN, etc.

# Install dependencies (frontend npm + backend/workers via uv)
./scripts/bootstrap.sh

# Apply database migrations
./scripts/migrate.sh

# Start all services for local development
./scripts/dev.sh
```

- Interactive API docs: `http://127.0.0.1:8000/docs`
- Dashboard: `http://127.0.0.1:3000` (or `FRONTEND_PORT`)

### Backend API surface (summary)

Routers under `/api/v1` include (non-exhaustive): **gateway**, **agents**, **events** (SSE), **idea-families**, **idea-scout**, **obsession**, **synthesis**, **repositories**, **overview**, **overlord**, **incidents**, **memory**, **settings**. Health routes are under `/health`.

## Analyst Configuration

The Analyst can run in multiple modes (see root `.env.example`):

- **`heuristic`** — Keyword/heuristic analysis (no LLM API key required for this mode)
- **`llm`** — Anthropic Claude (`ANTHROPIC_API_KEY`, `ANALYST_MODEL_NAME`)
- **`gemini`** — Gemini-compatible endpoint (for example `GEMINI_API_KEY`, optional `GEMINI_BASE_URL` / `GEMINI_MODEL_NAME`)

Set `ANALYST_PROVIDER` accordingly.

## Gateway Integration Contract

The control-plane boundary is `frontend → Agentic-Workflow backend → Gateway`. See `docs/gateway-integration-contract.md` for the canonical contract introduced in Story 1.2 and extended for multi-agent runtime assumptions in Story 1.3.

Story 1.4 adds `docs/configuration-ownership.md` as the canonical source for local configuration ownership and validation rules:

- OpenClaw owns `~/.openclaw/openclaw.json`, including Gateway auth and default model conventions.
- Agentic-Workflow owns local runtime paths, provider credentials (`GITHUB_PROVIDER_TOKEN`, `ANTHROPIC_API_KEY`, optional Gemini keys), and pacing/rate-limit thresholds in project env files.

## Relationship to OpenClaw

This repo is the Agentic-Workflow **control plane and dashboard** (`frontend/`, `backend/`, `workers/`). It does not replace the OpenClaw Gateway or OpenClaw-native agent definitions; it integrates with them via the documented Gateway contract and environment variables. If you keep a clone inside a larger workspace, scope changes to this project tree and follow `docs/configuration-ownership.md` for secret ownership.

## Security Model

Localhost-first, single-operator MVP. No authentication or RBAC in this phase. Do not commit `.env` files or real tokens; they are listed in `.gitignore`.

## Public Release Checklist

Before making the repository public:

- Confirm **no secrets** in history or tracked files (use `.env.example` only for templates).
- Add a **LICENSE** if you want others to reuse the code (this repo does not ship one by default).
- Review `deployment/` and `docs/` for paths that reference your private machine layout.

## Deployment & Operator Docs

The `deployment/` folder contains a **QUICKSTART**, full deployment README, **API-REFERENCE**, **GATEWAY-INTEGRATION**, **CONTROL-PANEL-GUIDE**, checklists, and an index: see `deployment/INDEX.md`.

## Development & Tests

```bash
# Frontend (from frontend/)
npm run test          # or: npm run test:unit | test:e2e | test:component

# Backend (from backend/)
uv run pytest

# Workers (from workers/)
uv run pytest
```

## Architecture & Documentation

See `docs/` for:

- `AGENT_ARCHITECTURE.md`, `opportunity-engine-proposal.md`, `analyst-enhancement-master-plan.md`
- `analyst-enhancement-testing-guide.md` — Analyst implementation and website testing flow
- `gateway-integration-contract.md`, `configuration-ownership.md`, `multi-agent-runtime-assumptions.md`
- `deferrals.md` — Intentionally deferred follow-on work
- `storage-optimization-plan.md` — Storage/DB optimization notes
- Overlord / OpenClaw planning: `overlord-openclaw-agent-spec.md`, `overlord-openclaw-agent-prompt.md`, `openclaw-overlord-implementation-plan.md`, `overlord-openclaw-feedback.md`

Implementation roadmap for deep synthesis and Scout ↔ Idea Family flows: `PLAN-deep-synthesis.md`.
