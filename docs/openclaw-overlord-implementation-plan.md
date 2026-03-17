# OpenClaw Overlord Implementation Plan

## Purpose

This document describes the full implementation plan for making `Overlord`
work in the strongest possible form for Agentic-Workflow.

The core design decision is:

- **Agentic-Workflow Overlord** is the deterministic operational engine
- **OpenClaw Overlord** is the operator-facing intelligence, memory, and voice

This plan intentionally keeps those layers separate but tightly connected.

---

## Executive Summary

The best implementation is **not** to force everything into either:

- a pure backend control loop, or
- a pure conversational agent persona

Instead, Overlord should be implemented as a **two-layer supervisory system**:

### Layer A — Agentic-Workflow Overlord

Lives inside the `agentic-workflow` repository.

Responsibilities:
- fleet-health aggregation
- incident lifecycle
- safe remediation policies
- Telegram plumbing
- Overlord API surfaces
- Overlord UI surfaces
- deterministic control loop behavior

### Layer B — OpenClaw Overlord

Lives in OpenClaw workspace/memory/behavior, not inside the repo.

Responsibilities:
- operator-facing explanation
- selective escalation
- project memory and continuity
- preference-aware alerting
- interpreting repo Overlord state in plain language
- helping shape policy and operating decisions

### Guiding Principle

- **Repo Overlord handles reflexes**
- **OpenClaw Overlord handles judgment**

That is the cleanest and most durable architecture.

---

## Goals

The completed Overlord system should let the operator:

- understand the whole system from one supervisory perspective
- trust that safe operational problems are handled automatically
- receive only high-signal proactive communication
- ask natural questions like:
  - “what is happening?”
  - “what changed?”
  - “what should I do?”
  - “is this important?”
- distinguish clearly between:
  - current live state
  - stale/historical state
  - auto-recovered incidents
  - operator-required incidents

---

## Non-Goals

This implementation should **not**:

- make the browser a source of truth for runtime state
- bypass backend-owned normalization
- replace Gateway as authority for runtime/session state
- turn Overlord into just another worker with ambiguous authority
- store OpenClaw-native identity files inside the `agentic-workflow` repo
- rely on chat memory alone for project continuity

---

## Architectural Model

## 1. The Three Operational Layers

### 1.1 Reflex Layer

Implemented inside Agentic-Workflow.

Purpose:
- fast, deterministic, always-on operational behavior

Examples:
- detect provider exhaustion
- classify blocked state
- deduplicate incidents
- safely pause/resume agents
- reconcile stale runtime state
- emit normalized summaries

### 1.2 Executive Layer

Implemented through OpenClaw.

Purpose:
- understand what the reflex layer means
- explain it clearly
- apply operator-aware judgment
- reduce noise

Examples:
- “The system is technically healthy, but GitHub budget is thin.”
- “Analyst is blocked, but this is recoverable and low risk.”
- “This should not wake you up; it can wait until morning.”

### 1.3 Relationship Layer

Also implemented through OpenClaw.

Purpose:
- form the human-facing continuity and trust layer

Examples:
- remember alert preferences
- send useful summaries
- keep quiet when nothing matters
- adapt tone and frequency to the operator

---

## 2. Boundary Rules

### 2.1 Agentic-Workflow owns

- Overlord state aggregation
- incident lifecycle
- remediation policy engine
- notification transport hooks
- UI and API surfaces
- control loop execution
- persistence of operational state

### 2.2 OpenClaw owns

- Overlord identity/persona for conversation
- memory of operator preferences
- project-specific interpretation behavior
- proactive communication strategy
- supervisory routines that consume repo Overlord outputs

### 2.3 Shared contract

OpenClaw should interact with Agentic-Workflow through backend-owned surfaces,
not direct browser or random file scraping whenever avoidable.

Preferred sources for OpenClaw:
- Overlord summary API
- Overlord policy API
- overview summary
- incidents/failures views
- live/control surfaces when needed for confirmation

---

## Current State Assessment

The current implementation already includes most of **Layer A MVP**:

- Overlord backend service
- Overlord routes and schemas
- Overlord evaluation loop in backend lifespan
- policy settings for remediation and Telegram
- UI integration in control/live/overview surfaces
- focused tests

This means the next major work is not “invent Overlord from scratch.”

The next major work is to finish and formalize **Layer B: OpenClaw Overlord**.

---

## Target End State

When the design is complete:

### Repo side
The app can:
- monitor and classify health
- open/resolve incidents
- safely auto-remediate known-safe conditions
- expose summaries, policy, and operator actions
- send structured important notifications

### OpenClaw side
I can:
- explain the app’s state naturally
- proactively notify the operator only when appropriate
- remember the operator’s preferences and tolerance
- produce incident summaries and system digests
- act as the operator-facing Overlord companion

---

## Full Implementation Roadmap

# Phase 1 — Formalize the OpenClaw Overlord Layer

## Objective
Create the persistent, non-repo implementation of Overlord as an operator-facing
OpenClaw role.

## Deliverables

### 1.1 Overlord role definition file
Create a durable project-specific role file in the OpenClaw workspace.

Recommended file:
- `agentic-workflow-overlord.md`

Contents should define:
- mission
- boundaries
- sources of truth
- communication style
- escalation policy
- proactive behavior policy
- what counts as urgent
- what requires human approval
- how to interpret repo Overlord state

### 1.2 Long-term memory entry
Add long-term memory describing:
- what Agentic-Workflow is
- what Overlord means in this project
- that repo-side Overlord exists and is the operational engine
- that OpenClaw-side Overlord is the supervisory/operator-facing layer
- operator preferences once defined

Recommended locations:
- `MEMORY.md`
- supporting note in `memory/YYYY-MM-DD.md`

### 1.3 Operator preference capture
Define and store preferences for:
- proactive alert frequency
- quiet hours
- escalation thresholds
- acceptable autonomy
- preferred communication channel
- whether summaries should be terse or detailed

## Success Criteria
- OpenClaw has a stable role in the project
- that role is not dependent on ephemeral chat context
- future sessions can reconstruct the intended behavior quickly

---

# Phase 2 — Define OpenClaw’s Read Model

## Objective
Make OpenClaw consistently consume repo Overlord state using a repeatable,
trustworthy status path.

## Deliverables

### 2.1 Canonical state inputs
Document and use the primary inputs OpenClaw should check:
- `/api/v1/overlord/summary`
- `/api/v1/overlord/policy`
- `/api/v1/overview/summary`
- relevant incident/failure surfaces
- live/control pages only for operator-visible confirmation

### 2.2 Interpretation contract
Define how OpenClaw translates repo data into operator meaning.

Example mappings:
- `rate-limited` -> “safe to wait unless this persists beyond threshold”
- `blocked` + operator_action -> “human should intervene soon”
- `healthy` + recent auto-action -> “system recovered, no action needed”

### 2.3 Summary templates
Define repeatable summary shapes such as:
- current posture summary
- what changed recently
- what needs human action
- what Overlord did automatically
- what to watch next

## Success Criteria
- asking OpenClaw “what is going on?” produces a grounded, repeatable answer
- answers rely on consistent source material instead of ad-hoc exploration

---

# Phase 3 — Proactive Communication Policy

## Objective
Turn OpenClaw into a useful supervisory companion without making it noisy.

## Deliverables

### 3.1 Escalation matrix
Create explicit rules for when OpenClaw should proactively message.

Recommended default:

#### Message proactively for:
- blocked state lasting beyond threshold
- repeated failures across the same subsystem
- all GitHub tokens exhausted
- all Gemini-compatible keys exhausted
- system recovered after a major incident
- clear operator-required action

#### Stay quiet for:
- transient recoverable conditions
- auto-resolved stale-state cleanup
- harmless short cooldowns
- repetitive low-severity churn

### 3.2 Channel split
Recommended communication split:

#### Repo Overlord
- deterministic transport-level alerts
- optional Telegram notifications
- minimal, structured operational messages

#### OpenClaw
- interpreted summaries
- escalation with context
- recommendations
- post-incident explanation
- periodic human-friendly digests

### 3.3 Quiet-hours policy
Optional but recommended.

Examples:
- overnight silence except critical incidents
- defer noncritical summaries until next morning

## Success Criteria
- the operator gets signal, not spam
- OpenClaw acts like a calm operations chief, not a noisy bot

---

# Phase 4 — OpenClaw Heartbeat / Check Routine

## Objective
Create a lightweight ongoing supervisory routine for OpenClaw.

## Deliverables

### 4.1 Heartbeat checklist
Add a project-specific heartbeat routine or equivalent checklist that tells
OpenClaw how to review Agentic-Workflow state.

Suggested routine:
1. check Overlord summary
2. check active incidents
3. check operator todos
4. check whether status is blocked/rate-limited/operator-required
5. if important and useful, notify operator
6. otherwise remain quiet

### 4.2 Optional cron jobs
If preferred, define precise periodic checks using cron instead of heartbeat.

Recommended if:
- exact timing matters
- summaries should arrive at known times
- incident reviews should happen on a schedule

### 4.3 Daily digest mode
Optional later enhancement.

Digest can include:
- current health posture
- incidents opened/resolved
- any auto-actions taken
- outstanding operator work
- strategic risk notes

## Success Criteria
- OpenClaw can proactively supervise the project in a stable, low-noise way

---

# Phase 5 — Repo Overlord Maturity Improvements

## Objective
Finish remaining Layer A gaps and strengthen operational quality.

## Recommended work

### 5.1 Incident lifecycle hardening
- explicit open/resolved persistence model
- stronger deduplication
- suppression of historical false positives
- richer reason codes and lifecycle metadata

### 5.2 Telegram production hardening
- dedupe repeated notifications
- severity threshold enforcement
- recovery notifications only after meaningful incidents
- optional digest scheduling

### 5.3 Better narrative outputs
Improve repo Overlord summary quality for operator-facing use.

Examples:
- cleaner `headline`
- stronger `operator_todos`
- clearer `what_overlord_did`
- better differentiation between live and stale evidence

### 5.4 Advanced cooldown and pacing policy
- stagger Firehose and Backfill when GitHub budget is thin
- smarter resume ordering
- predictive warnings before exhaustion

### 5.5 Trend and anomaly detection
Later-phase enhancement:
- repeated retry loops
- throughput collapse
- analysis backlog pressure growth
- incident recurrence patterns

## Success Criteria
- repo Overlord becomes a robust control-plane engine, not just an MVP shell

---

# Phase 6 — OpenClaw as Postmortem / Strategy Layer

## Objective
Use OpenClaw for the higher-level intelligence that deterministic loops are bad at.

## Deliverables

### 6.1 Incident explanation mode
OpenClaw can answer:
- what happened
- why it happened
- what was auto-fixed
- what remains risky
- whether policy should change

### 6.2 Pattern memory
OpenClaw remembers recurring patterns such as:
- “GitHub exhaustion often appears after paired Firehose/Backfill runs”
- “Analyst failures cluster around provider instability”
- “stale-state mismatches tend to look worse than they are”

### 6.3 Policy tuning proposals
OpenClaw can recommend changes like:
- raising/lowering alert thresholds
- changing quiet-hour behavior
- enabling/disabling aggressive auto-resume
- improving operator summaries

## Success Criteria
- OpenClaw becomes useful not just during incidents, but after them
- the system improves over time instead of repeating the same mistakes

---

## Recommended Deliverables by Ownership

## Agentic-Workflow Repo Deliverables

Already started or present:
- Overlord service layer
- Overlord API routes
- Overlord UI surfaces
- remediation policy settings
- control loop
- tests

Still recommended:
- stronger incident persistence/lifecycle
- production-quality Telegram dedupe and digest behavior
- richer narrative outputs
- anomaly/trend logic

## OpenClaw Workspace Deliverables

To create next:
- `agentic-workflow-overlord.md` role/spec file
- long-term memory entry in `MEMORY.md`
- daily note entry capturing the Overlord model
- heartbeat/check routine for project supervision
- operator preference record

---

## Communication Model Recommendation

## Default model

### Repo Overlord should communicate:
- machine-safe operational alerts
- deterministic important events
- dashboard/UI summaries

### OpenClaw should communicate:
- interpreted summaries
- recommendations
- operator guidance
- post-incident explanation
- occasional strategic observations

## Why this split works

Because repo Overlord is best at:
- certainty
- repeatability
- policy enforcement
- always-on behavior

And OpenClaw is best at:
- judgment
- narrative clarity
- memory
- context
- adapting to human preferences

---

## Proposed Autonomy Levels

### Level 1 — Advisory
Repo Overlord observes and reports.
OpenClaw explains.
No meaningful auto-remediation.

### Level 2 — Safe Autonomy
Repo Overlord auto-pauses/resumes/reconciles clearly safe conditions.
OpenClaw supervises, explains, and escalates selectively.

### Level 3 — Strategic Assistance
Repo Overlord handles safe operations.
OpenClaw provides periodic summaries, policy suggestions, and trend analysis.

## Recommendation
Start with **Level 2**.

That gives strong value without overreaching.

---

## Risks and Mitigations

## Risk 1: Duplicate alerts
### Mitigation
- strict channel split
- repo Overlord for raw alerting
- OpenClaw for interpretation only when useful

## Risk 2: OpenClaw becomes too chatty
### Mitigation
- explicit escalation rules
- heartbeat discipline
- preference memory
- quiet hours

## Risk 3: Source-of-truth drift
### Mitigation
- OpenClaw reads backend-owned surfaces
- no browser-side authority
- no duplicated hidden state models

## Risk 4: Operator trust erosion
### Mitigation
- always explain uncertainty
- log what was auto-fixed
- never silently take destructive actions
- separate recommendation from fact when needed

## Risk 5: Overfitting to current incidents
### Mitigation
- preserve architectural boundaries
- keep policy explicit
- review and evolve thresholds with experience

---

## Immediate Next Actions

The best next implementation steps are:

1. create the OpenClaw-side Overlord role/spec file
2. write long-term memory entries for the project and operator preferences
3. define proactive communication and escalation rules
4. add a lightweight heartbeat/check routine for Agentic-Workflow supervision
5. optionally harden repo Overlord notification and incident persistence behavior

---

## Best Final Design

The best final design is:

### Agentic-Workflow Overlord
- the operational nervous system
- the deterministic control-plane engine
- the source of structured health and incident state

### OpenClaw Overlord
- the operator-facing mind
- the interpreter
- the explainer
- the memory-bearing supervisory intelligence

## Final Principle

**Overlord should not be just a loop, and it should not be just a persona.**

It should be a layered supervisory system where:
- the repo provides the machinery
- OpenClaw provides the intelligence
- the operator gets one coherent experience

That is the strongest implementation path for this project.
