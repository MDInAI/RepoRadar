# Gateway Integration Contract

Story 1.2 establishes the control-plane boundary between Agentic-Workflow and OpenClaw Gateway. The goal is to make later runtime, configuration, and readiness work build on one explicit contract instead of inventing new access paths.

Story 1.3 extends that contract by making the MVP runtime target explicitly
multi-agent and by reserving named-agent runtime/session placeholders on the
same backend-owned surfaces.

Story 1.4 now fixes the configuration ownership split that feeds those surfaces:
Gateway transport details are read from OpenClaw-owned config, while
Agentic-Workflow keeps ownership of project-local runtime paths, provider
credentials, and pacing thresholds. See
`docs/configuration-ownership.md` for the canonical breakdown.

## Canonical Runtime Flow

`frontend -> Agentic-Workflow backend -> Gateway`

- The frontend reads control-plane data only from Agentic-Workflow backend routes.
- The backend owns normalization, error mapping, and future Gateway transport details.
- Gateway remains the source of truth for session discovery, routing context, and control-plane runtime status.

## Ownership Boundary

| Owner | Canonical state | Notes |
| --- | --- | --- |
| Gateway | Session inventory, session detail/history, routing context, runtime connectivity/status | These concerns stay Gateway-backed even when Agentic-Workflow reshapes them for the UI. |
| Agentic-Workflow | App-facing schemas, route contracts, named-agent runtime placeholders, repository pipeline data, analysis artifacts | The app translates Gateway data into typed backend-owned responses for the frontend. |
| Workspace | Checked-out repositories, local runtime artifacts, operator notes, diagnostic context | Workspace files may assist diagnosis but do not define the system contract for session or runtime authority. Project runtime storage remains separate from OpenClaw-native session files. |

## Multi-Agent Runtime Target

- MVP runtime mode is explicitly `multi-agent`.
- Initial named-agent assumptions are `Overlord`, `Firehose`, `Backfill`,
  `Bouncer`, and `Analyst`.
- `Combiner` and `Obsession` are reserved roles in the contract and do not need
  to be active yet.
- Runtime and monitoring models are shaped around collections of named agents,
  not singular-only placeholders.
- Session identity remains distinct from agent identity even when session views
  carry agent context.

## MVP Canonical Interfaces

The app treats these Gateway interfaces as authoritative for MVP and near-term follow-up stories:

1. Connectivity and runtime inspection for readiness or degraded-state reporting
   with explicit multi-agent runtime mode and named-agent placeholders.
2. Session discovery for normalized session collections that can carry
   agent-specific context.
3. Session detail and history when the UI needs per-session drill-down.
4. Gateway-backed real-time events that the backend will normalize before the frontend consumes them.

Story 1.2 publishes the backend-owned route surfaces now:

- `/api/v1/gateway/contract`
- `/api/v1/gateway/runtime`
- `/api/v1/gateway/sessions`
- `/api/v1/gateway/sessions/{session_id}`
- `/api/v1/gateway/sessions/{session_id}/history`
- `/api/v1/gateway/events/envelope`

These endpoints define shapes and ownership without turning the frontend into a direct Gateway client.

## Explicit Non-Contract Paths

The following paths are not the primary integration contract:

- `~/.openclaw/agents/*/sessions/sessions.json`
- `~/.openclaw/agents/*/sessions/*.jsonl`

If a future story ever introduces file-based inspection, it must be diagnostic-only, explicitly opt-in, and never a replacement for the Gateway-backed contract.

`~/.openclaw/openclaw.json` is now a read-only backend service input for
configuration ownership and validation. It is not a route-level or browser-level
integration path.

## Event Envelope for Later Streaming

When Gateway real-time updates are bridged to the frontend, Agentic-Workflow will emit a backend-owned normalized envelope with these fields:

- `event_id`
- `event_type`
- `session_id`
- `route_key`
- `occurred_at`
- `payload`

This keeps raw Gateway frames behind backend services and gives the frontend one stable event shape to consume.

## Dependency Chain

- Story 1.2 defines the Gateway authority boundary and app-owned contract.
- Story 1.3 layers multi-agent runtime assumptions and named-agent placeholders
  on top of this contract.
- Story 1.4 formalizes configuration ownership for Gateway URL, token, and related settings.
- Story 1.5 consumes the contract for readiness and connectivity UX.

## Guardrails

- Do not add direct browser-to-Gateway control-plane reads for MVP.
- Do not let route modules or frontend components read `~/.openclaw/openclaw.json` directly.
- Do not import low-level Gateway transport helpers from API route modules.
- Keep `/health` project-local; Gateway connectivity belongs under `/api/v1/gateway/*`.
- Reuse backend-owned normalized schemas instead of returning raw transport payloads.
- Do not regress the runtime contract to single-agent-only fields such as
  `current_agent` or `agent_status`.
