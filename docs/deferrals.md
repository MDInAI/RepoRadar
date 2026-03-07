# Deferred Work — Agentic-Workflow

This document records explicit deferrals from Story 1.1 to keep the scaffold focused and avoid premature implementation.

## Story 1.2 — Gateway Integration Contract

Story 1.2 is now implemented in [`docs/gateway-integration-contract.md`](./gateway-integration-contract.md)
plus the backend-owned `/api/v1/gateway/*` contract surfaces.

Remaining follow-on work is intentionally deferred:

- Live Gateway connection establishment and connectivity checks
- Population of normalized runtime/session data from Gateway
- Backend-bridged real-time event streaming implementation
- Readiness UX that consumes the new contract

## Story 1.3 — Multi-Agent Runtime Assumptions

- Live agent registration and runtime activation
- Agent registration and lifecycle management
- Inter-agent coordination patterns
- Agent memory persistence beyond placeholder storage dirs
- Overlord health monitoring integration

**Rationale:** Story 1.3 now fixes the multi-agent target, named-agent roster,
and ownership split in docs and typed contracts. Live orchestration still lands
later on top of the Gateway-backed contract.

## Story 1.4 — Local Configuration Through OpenClaw-Conformant Settings

- Per-agent model assignment editing UX
- Operator-facing configuration remediation flows
- Connectivity probes that act on the validated config surface
- Detailed per-channel configuration management UI

**Rationale:** Story 1.4 now defines ownership, masking, and validation. Follow-on
stories still need live UX and remediation flows on top of that contract.

## Story 1.5 — Readiness and Gateway Connectivity UX

- System health dashboard with live connectivity status
- Gateway ping / health check from frontend
- Service readiness indicators
- Connection error handling and recovery UX

**Rationale:** Readiness UX should consume the new backend-owned
`/api/v1/settings/summary` surface instead of direct file inspection or
frontend-owned transport settings.

## Additional Deferred Items

- **Database schema design** (Story 2.1) — Queue, repository state, and agent run tables
- **WebSocket event taxonomy** — Detailed event types and subscription channels
- **Feature APIs** — All CRUD/query endpoints beyond `/health`
- **TanStack Query integration** — Server state management hooks
- **Auth/RBAC** — Deferred post-MVP
- **Named-agent runtime activation** — `Combiner` and `Obsession` stay reserved
  contract roles until later synthesis stories
