# Agentic-Workflow

A local-first orchestration and operator dashboard for intelligent repository discovery, analysis, and idea synthesis — built as a separate localhost application connected to OpenClaw.

The control-plane integration boundary is `frontend -> Agentic-Workflow backend -> Gateway`. See
`docs/gateway-integration-contract.md` for the canonical contract introduced in
Story 1.2 and extended for explicit multi-agent runtime assumptions in Story
1.3. Story 1.4 adds `docs/configuration-ownership.md` as the canonical source
for local configuration ownership and validation rules.

## Project Structure

```
agentic-workflow/
├── frontend/    # Next.js App Router dashboard (agentic-workflow-ui)
├── backend/     # FastAPI control-plane API
├── workers/     # Python worker/scheduler processes
├── docs/        # Project documentation
├── scripts/     # Development & operational scripts
└── runtime/     # Generated data, logs, and temp files (gitignored)
```

## Runtime Topology

Three local service areas run independently:

1. **Dashboard Frontend** — Next.js dev server (`frontend/`)
2. **Control API** — FastAPI/Uvicorn (`backend/`)
3. **Worker Processes** — Python schedulers and jobs (`workers/`)

The MVP targets multi-agent operation from the start. Initial named-agent
assumptions are `Overlord`, `Firehose`, `Backfill`, `Bouncer`, and `Analyst`,
with `Combiner` and `Obsession` reserved for later specialization.

## Quick Start

```bash
# Bootstrap all services
./scripts/bootstrap.sh

# Start all services for local development
./scripts/dev.sh

# Run database migrations (backend)
./scripts/migrate.sh
```

## Out of Scope

The following existing OpenClaw-native paths are **not** part of this project and must not be modified:

- `dashboard/` — OpenClaw native dashboard
- `agents/` — OpenClaw agent definitions
- `workspace/mission-control/` — Separate workspace project
- Top-level Gateway/runtime files

## Deferred Work

The following concerns are deferred to later stories:

- **Story 1.5** — Local readiness and Gateway connectivity UX
- **Story 2.1+** — Database schema, queue logic, feature APIs, WebSocket events

Stories 1.2 and 1.3 themselves are no longer deferred; later stories extend the
Gateway-backed, multi-agent contract rather than redefining runtime mode or
ownership.

## Configuration Ownership

Story 1.4 formalizes the split between OpenClaw-native config and
project-owned settings:

- OpenClaw owns `~/.openclaw/openclaw.json`, including Gateway auth, channel
  conventions, and default model conventions.
- Agentic-Workflow owns local runtime paths, provider credentials, and
  pacing/rate-limit thresholds in project env files.
- The frontend only consumes backend-owned summaries and should only need
  `NEXT_PUBLIC_API_URL`.

Use `/api/v1/settings/summary` as the app-owned inspection surface for later
readiness UX.

## Security Model

Localhost-only single-operator MVP. No authentication or RBAC in this phase.

## Architecture

See `docs/` for detailed architecture documentation and `_bmad-output/planning-artifacts/architecture.md` for the full architecture decision document.

For the current Analyst implementation and website testing flow, see `docs/analyst-enhancement-testing-guide.md`.
