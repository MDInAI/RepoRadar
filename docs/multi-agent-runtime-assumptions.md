# Multi-Agent Runtime Assumptions

Story 1.3 makes the MVP runtime target explicit: Agentic-Workflow assumes
multi-agent operation from the start and layers that assumption on top of the
Story 1.2 Gateway integration contract.

## Runtime Target

- MVP runtime mode is `multi-agent`.
- The frontend continues to consume runtime and session data only through
  Agentic-Workflow backend routes under `/api/v1/gateway/*`.
- Gateway remains the control-plane authority for sessions, routing context,
  and runtime status.

## Named-Agent Roster

The app-owned roster vocabulary is fixed early so later stories extend one
contract instead of redefining agent identity:

| Agent key | Display name | Story 1.3 scope |
| --- | --- | --- |
| `overlord` | `Overlord` | Initial MVP role |
| `firehose` | `Firehose` | Initial MVP role |
| `backfill` | `Backfill` | Initial MVP role |
| `bouncer` | `Bouncer` | Initial MVP role |
| `analyst` | `Analyst` | Initial MVP role |
| `combiner` | `Combiner` | Reserved for later specialization |
| `obsession` | `Obsession` | Reserved for later specialization |

Story 1.3 does not require live orchestration for these roles. It reserves the
typed contract fields that later queueing, monitoring, and synthesis stories
will populate.

## Ownership Split

| Concern | Owner | Reason |
| --- | --- | --- |
| Session discovery, routing, control-plane runtime views | Gateway | OpenClaw Gateway remains the source of truth. |
| Normalized runtime/session API responses and named-agent contract fields | Agentic-Workflow | The app owns frontend-facing response shapes and documentation. |
| Project-local runtime storage and artifacts | Agentic-Workflow project runtime | Storage stays project-owned and separate from OpenClaw-native session files. |

## Contract Shape Assumptions

- Runtime surfaces must expose `runtime_mode="multi-agent"`.
- Runtime and monitoring views are modeled around collections of named agents,
  not a single global agent status blob.
- Named-agent records carry both a stable app-owned `agent_key` and a distinct
  `agent_role` so future Gateway runtime identity does not collapse into one
  field.
- Session identity stays distinct from agent identity.
- Session surfaces may carry agent context, but they do not replace Gateway as
  the session authority.
- Queue, lifecycle, monitoring, and session-affinity fields are placeholder
  contract fields in Story 1.3 and become live in later stories.

## Guardrails

- Do not add single-agent-only contract fields such as lone `current_agent` or
  `agent_status` to the backend-owned Gateway contract surfaces.
- Do not read OpenClaw session files directly as the primary runtime source.
- Do not build agent controls, WebSocket bridging, or persistence in this
  story.
- Do not move authority for sessions or routing away from Gateway.
