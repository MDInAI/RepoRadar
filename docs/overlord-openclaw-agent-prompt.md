# Prompt For OpenClaw: Build The Overlord Agent

Use this prompt in OpenClaw to create and wire the real `Overlord` agent for
Agentic-Workflow.

## Prompt

You are OpenClaw. I want you to create and connect the real `Overlord` agent
for the Agentic-Workflow project.

Context:

- Project root: `/Users/bot/.openclaw/workspace/agentic-workflow`
- Today, `Overlord` is only a placeholder in the roster.
- The project already has working monitoring surfaces, incidents, pause/resume,
  runtime progress, GitHub token-pool monitoring, and Gemini key-pool
  monitoring.
- The goal is to make `Overlord` become the real supervising control-plane
  agent for this project.

Read first:

- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/AGENT_ARCHITECTURE.md`
- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/gateway-integration-contract.md`
- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/multi-agent-runtime-assumptions.md`
- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/configuration-ownership.md`
- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/overlord-openclaw-agent-spec.md`
- `/Users/bot/.openclaw/workspace/agentic-workflow/docs/overlord-openclaw-feedback.md`

Mission:

Implement `Overlord` as the operational brain of Agentic-Workflow so it can:

1. Monitor all agents and runtime health
2. Understand incidents and resolve safe cases automatically
3. Distinguish live state from stale historical state
4. Explain the system in plain language
5. Notify me through Telegram when important things happen
6. Give me the option to enable or disable automatic remediation policies

Important correction before you design files:

- do not create `agents/overlord/*` inside the `agentic-workflow` repository
- this repository explicitly treats `agents/` as out of scope
- if you want OpenClaw-native identity / prompt / memory files, place them in
  the OpenClaw agent environment instead
- inside this repository, implement only the Agentic-Workflow side:
  backend services, worker/control logic, notification adapters, APIs, UI, and
  tests

What Overlord must do:

- aggregate state from the backend-owned surfaces instead of inventing a
  parallel source of truth
- monitor:
  - pause states
  - latest runs
  - runtime progress
  - failure events
  - GitHub token-pool state
  - Gemini/Haimaker key-pool state
  - backlog pressure
- classify incidents into:
  - healthy
  - degraded
  - blocked
  - rate-limited
  - operator-required
  - auto-recovering
  - stale-state-mismatch
- perform safe auto-actions:
  - safe pause
  - safe resume
  - safe retry
  - stale-state cleanup
  - resolved-alert cleanup
  - cooldown-aware retry scheduling
- never expose raw secrets
- never take destructive actions silently
- clearly explain:
  - what happened
  - why it happened
  - what Overlord did
  - what I still need to do

Telegram requirement:

Add optional Telegram notifications for major incidents and recoveries.

Create the configuration path and code needed for:

- `OVERLORD_TELEGRAM_ENABLED`
- `OVERLORD_TELEGRAM_BOT_TOKEN`
- `OVERLORD_TELEGRAM_CHAT_ID`
- `OVERLORD_TELEGRAM_MIN_SEVERITY`
- `OVERLORD_TELEGRAM_DAILY_DIGEST_ENABLED`

Telegram should notify only for important things, not every event.

Examples:

- all GitHub tokens exhausted
- all Gemini keys exhausted
- Analyst blocked for too long
- system recovered after a major incident
- optional daily digest

Implementation expectations:

- do not replace Gateway as authority for runtime/session surfaces
- do not bypass backend-owned API contracts
- keep frontend talking only to Agentic-Workflow backend routes
- separate OpenClaw-native identity assets from Agentic-Workflow repo code
- integrate Overlord into existing `/live`, `/overview`, `/agents`, and
  `/control` surfaces
- make Overlord visible as a real agent, not a placeholder
- create backend services and persistence only where needed
- prefer explicit policy-driven behavior over magic

Operator UX expectations:

- one place to see what Overlord knows
- one place to see what Overlord did automatically
- one place to see what still needs manual attention
- clear explanations for rate limits, pauses, retries, queue pressure, and
  stale state

Please do the work in this order:

1. Read the current project and Overlord spec
2. Read the feedback doc and keep the correct boundaries
3. Produce a concrete implementation plan
4. Implement the backend Overlord state aggregation and incident lifecycle
5. Implement Overlord safe auto-remediation policies
6. Implement Telegram notification support
7. Expose Overlord status/actions clearly in the website
8. Add tests
9. Verify the stack end to end
10. Write a short operator guide for Overlord

Important design rule:

Overlord is not just another worker. It is the supervising control-plane agent
for the whole project.

Implementation shape:

Treat Overlord as four subsystems working together:

1. State Aggregator
2. Incident Manager
3. Remediation Policy Engine
4. Operator Voice

Success condition:

When I open the website, I should be able to understand the entire system from
Overlord's perspective, trust its explanations, receive high-signal alerts, and
let it safely auto-fix the clear operational problems.
