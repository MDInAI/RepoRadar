# Opportunity Engine Proposal

## Thesis

Do not treat this as a "parse every repository deeply" problem. Treat it as a
multi-stage ranking and synthesis problem:

1. Ingest everything cheaply.
2. Normalize and deduplicate aggressively.
3. Cluster repositories into "same idea" families.
4. Score clusters, not just repositories.
5. Spend expensive analysis only on the best clusters.
6. Synthesize a stronger product from the best parts of several projects.

That direction matches the current Agentic-Workflow shape much better than a
monolithic crawler. The existing Firehose, Backfill, Bouncer, and Analyst
pipeline is already the correct backbone for this.

## What The Current Project Already Gets Right

The current workspace already contains the right first-order architecture:

- `Firehose` for ongoing discovery of new and trending repositories
- `Backfill` for historical coverage
- `Bouncer` for cheap early rejection before model spend
- `Analyst` for README-level business analysis on accepted repositories
- `Overlord` for pacing, fault detection, and exact resume

This means the project should not pivot to a different architecture. It should
extend the current pipeline with two missing layers:

- `Similarity/Family` layer to group repositories solving the same problem
- `Synthesis` layer to combine multiple repositories into better product ideas

## Recommended System Shape

### Layer 0: Intake

Goal: see the entire ecosystem without deep parsing.

Input sources:

- GitHub REST search/list flows for MVP
- historical GitHub search windows through Backfill
- optional later bulk sources such as GH Archive snapshots/events

Persist only cheap canonical signals first:

- immutable GitHub repo ID
- owner/name/full name
- description
- stars, forks, watchers
- language and topics
- created/pushed/updated timestamps
- license
- archived/fork/template flags
- default branch

### Layer 1: Cheap Repository Fingerprint

Goal: create a low-cost identity and quality fingerprint for every repo.

Parse next:

- README
- dependency manifests
- key config files
- top-level file tree

Derive features:

- category
- intended user/persona
- maturity
- commercializability
- likely duplicates/forks
- repo type: product, library, framework, template, tutorial, dataset, toy app

This layer should remain deterministic or near-deterministic as much as
possible. Reserve LLM calls for ambiguous cases.

### Layer 2: Idea Family Clustering

Goal: stop thinking in single repositories and start thinking in solution
families.

Create a new first-class entity:

- `IdeaFamily`

Each family groups repositories that solve the same user problem, for example:

- self-hosted form builders
- open-source CRM systems
- agent orchestration frameworks
- workflow automation platforms
- auth/identity stacks

Clustering input should mix:

- README embeddings
- topic overlap
- dependency overlap
- filename/config signatures
- shared problem vocabulary
- optional manual operator curation

This is the most important missing capability in the current project.

### Layer 3: Opportunity Scoring

Score families, not just repos.

Suggested score axes:

- `Demand`: stars velocity, contributor activity, issue/PR heat, recency
- `Quality`: docs, tests, releases, maintenance cadence
- `Buildability`: license clarity, modularity, understandable stack
- `Whitespace`: missing enterprise features, missing distribution model,
  weak monetization, poor UX, no hosted offer
- `MergePotential`: complementary strengths across repos in the same family
- `PersonalFit`: matches your target customers, stack preferences, and
  shipping ability

Recommended ranking rule:

`opportunity_score = demand + whitespace + merge_potential + personal_fit - execution_risk`

### Layer 4: Deep Analysis

Run expensive analysis only for:

- top families
- newly accelerating families
- manually starred families
- families with strong merge potential

At this layer, parse:

- README in full
- selected issues and discussions
- releases/changelog
- architecture docs
- a small set of representative source files

Do not read full codebases for the long tail.

### Layer 5: Synthesis

This is the real differentiator.

Add two first-class agents already implied by the PRD:

- `Combiner`: takes 2-5 repositories or families and proposes the best merged
  product
- `Obsession`: continuously refines one family or one candidate idea as new
  repos arrive

The synthesis output should not be free-form text only. Persist structured
artifacts:

- target user
- problem statement
- best feature set by source repo
- architecture recommendation
- monetization paths
- missing features to add
- moat/risk analysis
- "build now / watch / ignore" recommendation

## How To Handle Millions Of Repositories

The answer is storage separation plus progressive spend.

### Keep SQLite For Control Plane, Not For Everything

SQLite is still correct for:

- queue state
- lifecycle state
- current repo catalog
- operator-facing queries
- idea families
- scores
- starred items
- incidents and agent state

But if you truly plan to cover millions of repositories across history and
continuous updates, do not force all raw event and wide feature data into the
same operational store.

Recommended split:

- `SQLite`: serving database for current product state
- `Parquet + DuckDB` or `ClickHouse`: historical analytics/event lake
- local filesystem/object-like artifact store: README snapshots, analysis
  artifacts, synthesis outputs
- vector index: family similarity search

Practical rule:

- SQLite owns the latest canonical record and dashboard queries
- analytical storage owns large append-only history

### Use A Funnel Budget

For 1,000,000 repositories:

- 1,000,000 get metadata-only intake
- 200,000 get README + manifest parsing
- 20,000 get family-level clustering attention
- 2,000 get deep family scoring
- 200 get issue/source/release analysis
- 20 become active synthesis candidates

That is how you scale token spend and still cover the full ecosystem.

### Make Reprocessing Event-Driven

Do not reanalyze everything on every cycle.

Re-run only when:

- stars/activity moved materially
- README changed materially
- a family gained several new members
- a repo was manually starred
- a family crossed an opportunity threshold

## What To Prioritize First

### Best First Category

Start with:

- developer tools
- AI agent infrastructure
- workflow automation

More specifically, the best first parse target is:

- open-source B2B tools with clear operational pain and repeated feature
  patterns

Why this category first:

- high merge potential across many repos
- strong monetization paths
- README content is usually informative
- missing enterprise features are easy to detect
- easier to compare quality across projects
- closer to your current OpenClaw and agentic-workflow domain

### Categories To Parse Early

Priority order:

1. AI agent frameworks, orchestration, evals, memory, tool routing
2. Developer productivity and internal tools
3. Workflow automation, CRM, support, forms, dashboards, notifications
4. Security, auth, compliance, and observability tools
5. Data/infra and self-hosted operational platforms

### Categories To Deprioritize

Do not spend early budget on:

- games
- portfolio sites
- tutorials
- dotfiles
- lists/awesome repos
- coding challenge answers
- school/homework repos
- art/novelty projects

These create noise and weak synthesis value.

## What To Parse First Inside Each Repository

Recommended parse order:

1. repo metadata
2. description + topics
3. README
4. dependency manifests and config files
5. release metadata
6. selected issues/PR summaries
7. representative code files
8. commit history only for winners

This should become an explicit stage budget in the worker system.

## Product-Level Recommendation For This Project

The next strategic move for Agentic-Workflow should be:

### 1. Add Idea Families As A Core Data Model

Without this, the project remains a repository analyzer instead of an
opportunity engine.

Minimum new entities:

- `idea_family`
- `idea_family_member`
- `family_score_snapshot`
- `synthesis_candidate`
- `synthesis_artifact`

### 2. Add A Family Builder Worker

New agent role:

- `family-builder`

Responsibilities:

- cluster accepted/analyzed repositories
- update family membership
- maintain family summaries
- detect emerging families

### 3. Add A Score Engine

New agent or deterministic service:

- `opportunity-scorer`

Responsibilities:

- compute family opportunity scores
- rank for dashboard display
- trigger synthesis work when thresholds are crossed

### 4. Add Combiner Before Full Obsession

`Combiner` should land before `Obsession`.

Reason:

- it creates the first clear user value
- it is easier to validate
- it can run on demand and on schedule
- it will produce the first "best merged product" artifacts

### 5. Keep OpenClaw As The Operator Surface

OpenClaw should remain the control plane for:

- alerts
- agent monitoring
- remote operator interaction
- intervention on hot ideas

Agentic-Workflow should remain the repo-intelligence and synthesis engine.

## Suggested Near-Term Build Order

1. Finish the current core pipeline through durable README analysis and catalog
   browsing.
2. Introduce `IdeaFamily` persistence and clustering jobs.
3. Add family-level dashboard views and ranking.
4. Add `Combiner` to generate merged product proposals from top families.
5. Add operator feedback loops: star, reject, pin, merge, split family.
6. Add `Obsession` for continuous refinement of high-conviction ideas.
7. Only after this, broaden source coverage and heavier code-level parsing.

## Bottom Line

The correct strategy is:

- parse all repositories lightly
- parse promising repositories moderately
- analyze only the top families deeply
- synthesize across families and repos, not just inside one repo

If you do that, the product becomes a compounding opportunity engine rather
than an expensive GitHub scraper.
