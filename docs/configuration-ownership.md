# Configuration Ownership

Story 1.4 fixes one configuration contract for local development so later UX and runtime work reuse the same boundaries instead of inventing new ones.

## Canonical Split

| Area | Owner | Source | Browser Access | Notes |
| --- | --- | --- | --- | --- |
| OpenClaw-native defaults | OpenClaw | `~/.openclaw/openclaw.json` | No | OpenClaw keeps ownership of default agent/model conventions and channel definitions. |
| Gateway transport auth and TLS flags | Gateway via OpenClaw config | `gateway.*` in `~/.openclaw/openclaw.json` | No | Agentic-Workflow reads these through backend services, masks secrets, and reuses shared Gateway URL validation. |
| Workspace context | Workspace / project operator | `OPENCLAW_WORKSPACE_DIR` | No | Points workers at local repos and runtime context without making workspace files the system contract. |
| Project runtime storage | Agentic-Workflow | `DATABASE_URL`, `AGENTIC_RUNTIME_DIR` | No | Database and local runtime paths are project-owned. |
| Project provider credentials | Agentic-Workflow | local backend/worker env files or shell env | No | Provider tokens stay outside committed files and are never returned raw to the UI. |
| Project pacing and rate limits | Agentic-Workflow | `GITHUB_REQUESTS_PER_MINUTE`, `INTAKE_PACING_SECONDS` | No | These are app-specific tuning values, not OpenClaw-native config. |
| Frontend API entrypoint | Agentic-Workflow | `NEXT_PUBLIC_API_URL` | Yes | The frontend only needs an app-facing backend URL. |

## Rules

- The browser only talks to Agentic-Workflow backend routes.
- Backend services may read `~/.openclaw/openclaw.json`; route modules and frontend route components must not.
- Gateway secrets, provider tokens, and raw OpenClaw config blobs must never be returned to the browser.
- Project env examples document where to place local values, but they do not commit real secrets.
- Agentic-Workflow may reference OpenClaw-native settings, but it should not mirror them into a second source of truth.

## Backend-Owned Inspection Surface

The canonical inspection route for this story is:

- `/api/v1/settings/summary`

That route returns:

- Ownership metadata for OpenClaw, Gateway, workspace, and project-owned settings
- Masked setting summaries
- Structured validation results

It does not return:

- Raw secrets
- Raw `openclaw.json` contents
- Direct filesystem listings
- Browser-usable Gateway credentials

## Validation Expectations

The backend treats these as explicit validation failures for the settings surface:

- Missing or unreadable `OPENCLAW_CONFIG_PATH`
- Invalid JSON in `~/.openclaw/openclaw.json`
- Missing `gateway.url`
- Missing `gateway.auth.token`
- Missing `agents.defaults.model`
- Missing project-owned runtime values such as `DATABASE_URL`

These failures use the same structured `422` semantics already used for Gateway transport validation.
