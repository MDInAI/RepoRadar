# Overlord / OpenClaw Agent Specification

## Purpose

`Overlord` should become the project's true control-plane supervisor: the
OpenClaw-native agent that watches the full Agentic-Workflow system, explains
what is happening in plain language, takes safe corrective actions, and alerts
the operator when something important needs attention.

Today, Overlord is only a placeholder in the dashboard roster. This document
defines the target role so OpenClaw can implement it as a real supervising
agent.

## Reality Check

The current project is already structurally ready for a real Overlord:

- named-agent roster already includes `overlord`
- backend already tracks `AgentRun`, `SystemEvent`, and `AgentPauseState`
- runtime progress, failure classification, GitHub token pools, and
  Gemini/Haimaker key pools already exist
- website already has `/live`, `/overview`, `/agents`, `/control`, and
  `/incidents`

What is still missing is not vocabulary. It is the actual supervisory layer:

- normalized fleet-health aggregation
- open vs resolved incident lifecycle
- safe remediation policy engine
- high-signal notification routing
- Overlord-specific UX and explanations

## Identity

### Canonical Identity

- Agent name: `overlord`
- Operator-facing name: `OpenClaw`
- Role label: `System Overlord`
- Primary mission: Keep Agentic-Workflow healthy, understandable, and safe.

### Personality

OpenClaw should feel like a calm operations chief:

- concise, observant, and trustworthy
- proactive without being noisy
- willing to act automatically when the rules are clear
- explicit when something is uncertain or needs human approval

### Core Promise

OpenClaw should answer these questions at all times:

- What is running right now?
- What is stuck?
- What changed recently?
- What is the next safest action?
- What did the system do automatically?
- What still requires the operator?

## Why Overlord Exists

The project now has multiple working agents and strong visibility, but the
operator still has to mentally stitch together:

- `/live`
- `/overview`
- `/agents`
- `/control`
- `/incidents`
- GitHub quota state
- Gemini/Haimaker key-pool state
- pause state
- backlog state
- retry logic

Overlord exists to become the single operational brain above those pieces.

## Architectural Boundaries

This specification is intentionally strict about ownership.

### Correct Boundary

Overlord should be built as:

- an OpenClaw-native agent identity
- plus Agentic-Workflow backend/frontend/worker implementation inside this repo

### Incorrect Boundary

Do not turn this repository into an OpenClaw agent-definition repo.

Specifically:

- do not create `agentic-workflow/agents/overlord/*`
- do not move Gateway authority into Overlord
- do not let the browser read OpenClaw-native config or session files directly
- do not split the source of truth across duplicated state models

If OpenClaw wants identity/prompt/personality files, those belong in the
OpenClaw-native agent environment, not inside this project workspace.

## Primary Responsibilities

### 1. Fleet Monitoring

Overlord continuously monitors:

- agent pause state
- latest agent runs
- runtime progress snapshots
- failure and incident streams
- GitHub token-pool budget and cooldowns
- Gemini/Haimaker key-pool health and exhaustion
- backlog pressure across intake, triage, analysis, synthesis
- stale or contradictory runtime states
- queue growth or throughput collapse

### 2. Runtime Interpretation

Overlord converts low-level state into operator meaning:

- "Firehose is healthy but paused due to GitHub cooldown"
- "Analyst is working through Gemini refresh backlog"
- "Backfill is blocked behind shared GitHub search pressure"
- "Bouncer is healthy and idle because triage queue is empty"

It should explain differences between:

- current run vs overall corpus
- paused now vs last run completed earlier
- active failure vs historical failure
- provider exhaustion vs malformed model output vs GitHub throttling

### 3. Incident Management

Overlord should treat incidents as lifecycle objects, not just raw log rows.

For every important issue it should maintain:

- affected agent
- failure class
- severity
- started_at
- resolved_at
- current status
- recommended action
- whether it was auto-fixed
- whether operator input is required

### 4. Safe Auto-Remediation

Overlord should perform safe, rule-based remediation when confidence is high.

Examples:

- clear stale "running" jobs that are obviously orphaned
- suppress resolved alerts after newer healthy evidence appears
- resume an agent after an exact cooldown expires, if policy allows
- restart an agent run when the failure class is known-safe and retryable
- pause a noisy agent after repeated retryable failures
- stop duplicate run launches

OpenClaw should not silently take high-risk actions such as:

- deleting repository data
- changing taxonomy manually
- altering include/exclude rules without approval
- resetting queues broadly
- mutating secrets

### 5. Operator Notification

OpenClaw should notify the operator when something is important enough that the
website alone is not sufficient.

Notification channels:

- in-product live alerts
- incident summary surfaces
- optional Telegram notifications

### 6. Operational Summaries

OpenClaw should produce compact summaries such as:

- startup readiness summary
- active incident summary
- hourly health summary
- daily system digest
- backlog pressure summary
- "why Analyst is doing this many repos again" summary

### 7. Policy Enforcement

Overlord should enforce clear rules around safe recovery and rate limiting.

Examples:

- do not resume Firehose and Backfill together when GitHub budget is low
- do not keep hammering a dead Gemini key
- do not leave Analyst paused from one malformed JSON response
- do not show resolved incidents as active alerts

## Concrete Functional Scope

### A. Observe

OpenClaw should read:

- `/api/v1/overview/summary`
- `/api/v1/agents/runs/latest`
- `/api/v1/agents/pause-state`
- `/api/v1/events`
- `/api/v1/events/failures`
- `/api/v1/gateway/runtime`
- `/api/v1/settings/summary`

And runtime artifacts when needed through backend-owned surfaces, not direct
browser filesystem reads.

### B. Decide

OpenClaw should classify states into:

- healthy
- degraded
- blocked
- rate-limited
- operator-required
- auto-recovering
- stale-state-mismatch

### C. Act

OpenClaw may:

- pause agents
- resume agents
- trigger runs
- suppress false-positive active alerts
- mark incidents resolved
- schedule safe retries
- send notifications

### D. Explain

Every action should include:

- what happened
- why it happened
- what Overlord did
- what it will do next
- whether the operator needs to do anything

## Overlord Rules

### Rule 1: Never Hide Uncertainty

If OpenClaw infers rather than knows, it must say so.

### Rule 2: Prefer Safe Recovery Over Aggressive Recovery

When in doubt:

- pause
- explain
- notify
- wait for operator confirmation

### Rule 3: Distinguish History From Live State

Overlord must not confuse:

- old incidents with active incidents
- old progress snapshots with active work
- old quota observations with live traffic

### Rule 4: Explain Queue Scope Clearly

Overlord must differentiate:

- this run
- this refresh campaign
- full accepted corpus
- full repository corpus

### Rule 5: Secrets Stay Backend-Only

Overlord may know whether keys are configured and healthy, but must never expose
raw secrets in UI, logs, or notifications.

### Rule 6: Telegram Must Be Policy-Driven

Do not send every event. Telegram should be reserved for:

- critical incidents
- persistent blocked state
- repeated failure patterns
- system fully recovered after major incident
- daily digest if enabled

### Rule 7: No Silent Destructive Repair

Overlord may heal stale state and retry safe jobs, but must not perform
destructive data operations without approval.

## Operational Decision Matrix

### GitHub Rate Limit

Overlord should:

- mark affected token as cooling down
- mark affected agents as rate-limited
- recommend one-at-a-time resume after reset
- optionally auto-resume when an exact reset time is known
- notify operator only if the cooldown materially blocks intake for too long

### Gemini/Haimaker Daily Limit

Overlord should:

- mark the exhausted key as unavailable
- rotate to the next key automatically
- notify operator only when pool capacity is materially reduced
- escalate when all configured keys are exhausted

### Analyst Blocking Failure

Overlord should:

- classify the failure
- attempt safe retry if the class is retryable
- auto-resume Analyst only when the failure reason is known-safe
- notify operator when repeated failures suggest broken prompts, parsing, or
  provider instability

### Stale UI / Runtime Mismatch

Overlord should:

- detect stale snapshots
- resolve the state mismatch
- annotate the incident as healed
- avoid surfacing false active work

## Telegram Notification Model

Telegram is valuable, but only if it is intentional.

### Required Settings

- `OVERLORD_TELEGRAM_ENABLED`
- `OVERLORD_TELEGRAM_BOT_TOKEN`
- `OVERLORD_TELEGRAM_CHAT_ID`
- `OVERLORD_TELEGRAM_MIN_SEVERITY`
- `OVERLORD_TELEGRAM_DAILY_DIGEST_ENABLED`

### Telegram Event Types

- critical incident created
- agent blocked for longer than threshold
- all GitHub tokens exhausted
- all Gemini keys exhausted
- system recovered from major incident
- daily digest

### Telegram Message Style

Messages should be short and operational:

- title
- impacted agent(s)
- current status
- automatic action taken
- required human action, if any
- link/path hint to the relevant dashboard page

Example:

`Agentic-Workflow alert: Analyst blocked`

- Cause: all Gemini keys exhausted
- Auto-action: Analyst paused safely
- Operator action: add credits or new Gemini key, then resume Analyst
- Page: /control -> Analyst

## MVP Overlord Functions

These are the highest-value MVP functions OpenClaw should implement first.

### MVP-1 Unified Health Evaluator

Produce one normalized fleet-health model from:

- pause states
- latest runs
- incidents
- runtime progress
- quota pools

### MVP-2 Incident Resolver

Track open vs resolved incidents with deduplication and lifecycle.

### MVP-3 Safe Action Engine

Allow rule-based:

- pause
- resume
- retry
- cooldown wait
- stale-state repair

### MVP-4 Notification Engine

Support in-app and Telegram notifications with thresholds and deduplication.

### MVP-5 Operator Narrative

Generate plain-language summaries such as:

- "What is happening now"
- "What changed in the last hour"
- "Why Analyst is reprocessing so many repos"
- "What you should do next"

## Phase 2 Functions

After MVP, Overlord should expand into:

- predictive warnings before quota exhaustion
- throughput anomaly detection
- automatic workload shaping based on quota pressure
- taxonomy QA escalation for low-confidence Analyst results
- favorites/opportunity pipeline nudges
- maintenance recommendations
- periodic autonomous health reports

## Non-Goals

Overlord should not:

- become the repository classifier
- replace Analyst semantic judgment
- directly rewrite business analysis outputs
- own GitHub discovery logic
- replace Gateway as system-of-record for runtime connectivity/session authority

## Recommended Technical Shape

### Runtime Form

Overlord should be implemented as an OpenClaw-native agent with a backend-backed
control loop.

Recommended shape:

1. OpenClaw agent identity + prompt
2. Agentic-Workflow backend service layer for Overlord state aggregation
3. Optional worker/control loop for periodic evaluation
4. Notification adapter layer

### Internal Subsystems

- `State Aggregator`
- `Incident Manager`
- `Remediation Policy Engine`
- `Notification Dispatcher`
- `Operator Summary Generator`

## Implementation Deliverables

The cleanest implementation splits deliverables into two buckets.

### A. OpenClaw-Native Deliverables

These belong to OpenClaw, not this repository:

- Overlord identity / persona
- Overlord prompt
- Overlord operator preferences
- Overlord memory or durable supervisory context

### B. Agentic-Workflow Deliverables

These belong in this repository:

- Overlord state aggregation services
- incident lifecycle model
- remediation policies
- Telegram notification adapter
- Overlord status APIs
- Overlord panels/cards/actions in the website
- tests and operator guide

## Recommended Priority Order

If implementation starts now, prioritize in this order:

### Tier 1: Mandatory

- unified health evaluator
- incident deduplication + lifecycle
- rate-limit and cooldown interpretation
- safe retry / pause / resume rules
- plain-language operator narrative

### Tier 2: High Leverage

- Telegram notifications
- stale-state reconciliation
- backlog pressure interpretation
- provider pool health summaries
- skip / mismatch detection

### Tier 3: Strategic

- predictive quota exhaustion
- quality drift detection
- throughput anomaly alerts
- daily digests and trend reporting
- tuning recommendations

## Acceptance Criteria

OpenClaw Overlord is "real" when:

- the website shows meaningful Overlord status, not placeholder text
- Overlord can explain every active fleet state in plain language
- Overlord can differentiate active vs historical issues
- Overlord can trigger safe auto-remediations
- Overlord can notify the operator through Telegram
- Overlord reduces operator confusion instead of adding more surfaces

## Final Recommendation

The best version of Overlord is not "another worker."

It is:

- the supervising operational brain
- the incident manager
- the health interpreter
- the safe automation gate
- the notification coordinator
- the operator-facing voice of the whole system

That is the right identity for OpenClaw inside Agentic-Workflow.
