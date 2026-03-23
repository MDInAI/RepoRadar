# Storage Optimization Plan

## Objective

Reduce live storage growth in Agentic-Workflow so the project can scale from the current local-first corpus into:

- `100,000` repositories without becoming painful to operate
- `1,000,000+` repositories without wasting space on low-value history
- a future multi-million repository corpus with a clear migration path away from SQLite-heavy storage

This plan is based on the current measured project footprint, not a hypothetical design.

## Current Measured Footprint

Measured locally on `17 Mar 2026`:

- Whole project: `1.8G`
- Frontend: `1.2G`
- Runtime data: `302M`
- Backend: `144M`
- Workers: `106M`

The important distinction is:

- most of the **whole project** size is developer/build tooling
- most of the **scaling** size is live runtime data

### Current Runtime Data Breakdown

- SQLite database: `288M`
- README artifacts: `4.9M`
- Analysis artifacts: `2.9M`
- Analyst runtime files: `3.6M`
- Bouncer runtime files: `2.1M`

### Largest Live Database Consumers

Approximate top DB objects right now:

- `system_events`: `71.9M`
- `agent_runs`: `46.5M`
- `repository_artifact_payload`: `36.9M`
- `repository_analysis_result`: `23.3M`
- `ix_system_events_created_at`: `27.8M`
- `ix_system_events_event_type`: `19.2M`
- `ix_agent_runs_started_at`: `13.8M`

## Main Conclusion

The storage problem is **not** mostly:

- source code
- frontend UI code
- README files
- final Analyst summaries alone

The storage problem **is** mostly:

- event history
- run history
- repeated artifact payload retention
- keeping too much operational history live inside the main SQLite database

## What Will Grow With More Repositories

At `100,000` repositories and beyond, the primary growth will come from:

1. `repository_intake` and related repo metadata
2. `repository_artifact_payload`
3. `repository_analysis_result`
4. `system_events`
5. `agent_runs`
6. indexes on those tables

These will **not** grow much with repo count:

- `frontend/node_modules`
- `frontend/.next`
- `backend/.venv`
- `workers/.venv`

## Scaling Principles

To make storage efficient at scale, the system should follow five principles:

1. Keep only the latest live truth in the main database.
2. Treat rejected and low-value repos as lightweight records.
3. Move old history out of the hot path.
4. Separate blobs from relational state.
5. Keep acceptance-quality intelligence, not endless duplicated evidence.

## Target Storage Model

### 1. Hot Live State

Keep in the primary operational database:

- current repository metadata
- current queue status
- current accepted/rejected status
- latest canonical analysis result
- current pause state
- latest runtime snapshots
- recent incidents and recent runs

This should be optimized for the UI, operators, and worker scheduling.

### 2. Warm Historical State

Keep as archive tables or compressed exports:

- old `system_events`
- old `agent_runs`
- old incident rows no longer needed for live dashboards
- old analysis versions

This should remain queryable, but not loaded into everyday operational paths.

### 3. Cold Blob Storage

Keep outside the main relational DB:

- raw README content
- raw provider payloads
- full evidence dumps
- archived analysis artifacts
- long-form prompt/response traces if retained

The main DB should store only references, hashes, and current summaries where possible.

## Measured Per-Stage Storage Cost

Using the current live database, the repo-specific storage cost is approximately:

- intake only (`Firehose` or `Backfill`): `755 bytes` per repo
- triage explanation (`Bouncer`): `164 bytes` per repo
- Analyst structured analysis row: `12.7 KB` per analyzed repo
- Analyst artifact payloads: `21.3 KB` per analyzed repo
- total Analyst impact: `34.1 KB` per analyzed repo

This leads to the most important scaling conclusion in the project:

- `Firehose` and `Backfill` are cheap
- `Bouncer` is cheap
- `Analyst` is the expensive per-repo step

### Current Equivalent Cost Per 1,000 Repositories

- intake only: about `0.72 MB`
- intake + bouncer: about `0.88 MB`
- intake + bouncer + Analyst on all 1,000 repos: about `33.35 MB`

### Current Equivalent Cost Per 10,000,000 Repositories

- intake only: about `7.0 GB`
- intake + bouncer: about `8.6 GB`
- intake + bouncer + Analyst on all 10,000,000 repos: about `333 GB`

This means the correct large-scale architecture is:

- parse everything minimally
- triage cheaply
- deeply analyze only a selected subset

## Selective Parsing and Analysis Strategy

This is the strategy that should govern the pipeline from now on if the goal is multi-million scale with minimal space.

### 1. Firehose and Backfill Become Minimal Discovery Layers

`Firehose` and `Backfill` should ingest all candidate repos in the same lightweight format:

- repository id
- owner/name/full name
- stars/forks
- pushed date / created date
- discovery source
- one short description
- queue state

They should **not** automatically trigger expensive README/evidence storage for every discovered repo.

### 2. Lightweight Signal Gate Before Deep Parsing

Before README fetch and full analysis, the pipeline should evaluate lightweight selectors such as:

- keyword match in repo name
- keyword match in short description
- star/fork thresholds
- activity freshness
- language allowlist
- known organization/owner allowlist
- manually curated watchlist

This gate should decide whether a repo is:

- `minimal_only`
- `candidate_for_bouncer_acceptance`
- `candidate_for_analyst`

### 3. Bouncer Remains Cheap and Deterministic

`Bouncer` should continue to do low-cost filtering and explanation only.

Its job at scale:

- reject obvious low-value repos cheaply
- accept repos that pass the include/exclude policy
- add a short explanation
- avoid fetching or retaining expensive artifacts itself

### 4. Analyst Becomes Explicitly Selective

`Analyst` should not run on the full discovered corpus by default.

It should run only for repositories that satisfy one or more of:

- accepted by Bouncer
- matched an operator-maintained keyword list
- matched a watchlist or favorite-owner rule
- passed a lightweight score threshold
- were manually promoted by the operator

This turns Analyst into a targeted intelligence layer rather than a universal enrichment step.

### 5. README Fetching Should Follow Selection

README and heavier evidence collection should happen only after a repo is promoted past the cheap filters.

This is one of the most important storage decisions in the whole system.

Good rule:

- minimal discovery first
- README/evidence only for shortlisted repos

## Recommended Pipeline Policy

The desired steady-state behavior is:

1. `Firehose` discovers broadly with minimal storage.
2. `Backfill` discovers broadly with the same minimal storage model.
3. lightweight keyword/signal gate scores whether the repo is worth deeper attention.
4. `Bouncer` applies deterministic acceptance/rejection rules.
5. only selected repos get README fetch, evidence build, and Analyst execution.
6. only favorites and strong opportunities get richer long-lived retention.

## Repository Storage Classes

To make this concrete, every repository should belong to one of these storage classes.

### 1. `minimal_only`

Keep only:

- intake metadata
- discovery source
- current triage state
- one short explanation if rejected

No README, no evidence payload, no analysis artifact.

### 2. `candidate`

Keep:

- minimal metadata
- triage explanation
- maybe one lightweight score or keyword-match reason

Still no full Analyst payload yet.

### 3. `accepted_standard`

Keep:

- latest README snapshot
- latest canonical analysis
- current category, tags, confidence, and recommendation

Archive older versions rather than keeping them live.

### 4. `favorite_enhanced`

Keep:

- current analysis
- deeper synthesis links
- operator curation
- stronger opportunity metadata

### 5. `opportunity_deep`

Keep:

- current full analysis
- deeper synthesis
- obsession/idea links
- richer historical context if truly useful

Only a small percentage of repos should ever reach this class.

## Optimization Plan

## Phase 1: Quick Wins Inside Current Architecture

Goal:
- cut unnecessary live growth without changing the core stack

### 1. Add event retention

Keep detailed `system_events` live for only a short horizon.

Recommendation:

- keep full event detail for `30 days`
- keep incident-resolution-important events for `90 days`
- archive older events into compressed JSONL or archive tables

Expected impact:

- largest immediate reduction in DB growth
- lower index growth
- faster incident queries

### 2. Add run retention

Keep detailed `agent_runs` only for recent operational visibility.

Recommendation:

- keep detailed runs for `30 days`
- roll older runs into daily aggregate summaries
- archive raw historical run rows

Expected impact:

- major DB savings
- cleaner monitoring queries

### 3. Keep only one live canonical analysis row per repo

Current principle:

- each repo should have one current “truth” analysis for normal app usage

Recommendation:

- keep only the latest canonical analysis in the live table
- move superseded analysis versions to archive storage

Expected impact:

- bounded analysis-result growth
- easier UI semantics

### 4. Stop storing rich payloads for rejected repos

For rejected repos, keep only:

- GitHub repo id
- owner/name
- stars/forks/language
- discovered timestamp
- reject timestamp
- triage reason
- maybe one short description

Do **not** retain:

- full README text
- full evidence artifacts
- large provider payloads
- repeated analysis artifacts

Expected impact:

- strong long-term savings because most low-value repos never become opportunities

### 5. Compress or deduplicate artifact payloads

Recommendation:

- hash README and artifact bodies
- reuse identical stored blobs when content has not changed
- avoid writing multiple identical payloads across re-analysis waves

Expected impact:

- direct reduction in `repository_artifact_payload`
- especially helpful during repeated Analyst refresh campaigns

### 6. Add a pre-Analyst selection gate

Introduce a lightweight promotion gate before README fetch and Analyst execution.

Recommended selectors:

- keyword lists
- owner allowlists
- minimum stars/forks/activity freshness
- manual promotion
- opportunity watchlists

Expected impact:

- largest reduction in future Analyst storage
- avoids paying `~34 KB` per repo for low-value candidates
- makes multi-million intake realistic

## Phase 2: Storage-Aware Data Model Hardening

Goal:
- prepare for `100k+` repos without operational pain

### 7. Split accepted and rejected storage policy

Use two classes of repository retention:

#### Accepted repos

Keep:

- latest full analysis
- lightweight selected artifacts
- current tags/category/confidence
- favorite/opportunity-related metadata

#### Rejected repos

Keep:

- minimal metadata
- reason for rejection
- enough context to avoid reprocessing mistakes

This is the single most important model change for efficient scaling.

### 8. Introduce archive tables or export jobs

Add explicit archive routines for:

- `system_events`
- `agent_runs`
- superseded `repository_analysis_result`
- optionally stale `repository_artifact_payload`

Archive format options:

- archive tables inside the same DB as an intermediate step
- compressed JSONL files in `runtime/data/exports`
- object storage in a later deployment phase

### 9. Add “latest only” indexes for operational paths

Keep indexes optimized for:

- latest runs
- latest active incidents
- current repo state
- current accepted backlog

Avoid carrying expensive indexes for large historical tables that the main UI no longer uses frequently.

## Phase 3: Million-Scale Architecture

Goal:
- make the platform credible beyond SQLite-sized workloads

### 10. Move operational state to Postgres

SQLite is fine for local-first development and modest production-like datasets.
It is not the right long-term home for millions of repos with large operational history.

At million-scale, use Postgres for:

- current repository metadata
- current queue state
- latest analysis state
- active incidents
- current run state

### 11. Move large text/blob storage out of the primary DB

Use object storage or compressed blob storage for:

- README snapshots
- raw evidence payloads
- full LLM raw outputs if retained
- archive exports

The relational DB should store:

- references
- hashes
- content metadata
- current structured summaries

### 12. Add storage tiers by repo value

Recommended repo classes:

- `rejected-minimal`
- `accepted-standard`
- `favorite-enhanced`
- `opportunity-deep`

Only the top classes should receive expensive retention and richer long-lived artifacts.

### 13. Make history opt-in for expensive entities

For multi-million scale, avoid unlimited history for:

- analysis versions
- raw provider traces
- large evidence payloads
- every alert repetition

Keep historical depth only where it adds real product or operator value.

## Recommended Implementation Order

1. Add the pre-Analyst selection gate
2. Event retention and archival
3. Run retention and rollups
4. Minimal rejected-repo storage policy
5. Latest-only live analysis policy
6. Payload deduplication/hashing
7. Archive jobs and export format
8. Postgres + blob-storage migration design

This order yields the best space savings early without forcing a full platform rewrite first.

## Expected Gains

### Short term

After Phases 1 and 2:

- slower DB growth
- smaller indexes
- faster incident and agent-monitoring queries
- less wasted storage on low-value repos

### Long term

At `100,000` repos:

- live DB remains focused on current state instead of all historical noise
- storage footprint grows more in proportion to accepted-value repos than total raw discovery count

At `1,000,000+` repos:

- primary relational state remains manageable
- blobs and archives scale independently
- storage cost becomes policy-driven instead of accidental

## Concrete Rules To Adopt

These are the simplest rules to implement and explain:

1. Keep full analysis only for accepted repos.
2. Keep only minimal metadata for rejected repos.
3. Add a keyword/signal gate before README fetch and Analyst execution.
4. Keep only the latest canonical analysis live.
5. Keep only recent events and runs live.
6. Archive old history on a schedule.
7. Deduplicate large text payloads by content hash.
8. Move raw blobs out of the main DB before million-scale.

## What This Means For Analyst

The Analyst does increase storage, but it should not dominate storage if handled correctly.

Good policy:

- do not analyze every discovered repo
- keep one latest structured analysis row live
- archive superseded analysis versions
- avoid retaining every raw prompt/response forever
- store large evidence bodies outside the main DB when possible

The final structured Analyst result is valuable.
The expensive part is retaining too many versions, traces, and surrounding event history.

## Acceptance Criteria

This storage plan is successful when:

- the live DB is no longer dominated by old events and runs
- rejected repos do not retain expensive full artifacts
- accepted repos keep a single canonical live analysis
- Analyst runs only on selected repos, not the full discovered corpus by default
- repeated refresh campaigns do not duplicate large payloads unnecessarily
- the project has an explicit archive path before `100k+` scale
- the migration path to Postgres + blob storage is documented before `1M+` scale

## Immediate Next Tasks

1. Define the pre-Analyst keyword/signal promotion rules.
2. Add retention-policy documentation and configuration knobs.
3. Design archive jobs for `system_events` and `agent_runs`.
4. Audit rejected-repo artifact retention and stop writing unnecessary blobs.
5. Add content-hash deduplication for README/artifact payload storage.
6. Define the live-vs-archived data contract for analysis results.

## Operator Note

If the goal is “millions of repos with minimum space,” the most important strategy is:

- **store rich intelligence only for high-value repos**
- **store lightweight state for the rest**

That is the difference between a scalable intelligence browser and an oversized historical dump.
