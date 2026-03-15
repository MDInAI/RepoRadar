# Analyst-First Opportunity Intelligence Roadmap

## Purpose

This document defines the recommended evolution of the project from a repository ingestion pipeline into a high-confidence opportunity intelligence system.

The plan is intentionally split into two layers:

1. `Analyst-first roadmap`
   Start here. This is the highest-leverage place to improve intelligence quality.
2. `Full-system roadmap`
   Expand the same ideas across Firehose, Backfill, Bouncer, Combiner, Overlord, and the operator surface.

The guiding principle is:

- the system should not only collect repositories
- it should help a founder discover, compare, validate, combine, and evolve product ideas with evidence

---

## Part I: Analyst-First Roadmap

### Why Analyst Comes First

The current system is already reasonably capable at:

- discovering repositories
- tracking pipeline state
- exposing runtime truth
- showing raw operational visibility

The biggest weakness is not ingestion. It is intelligence quality.

Today the Analyst is:

- README-heavy
- heuristic
- fast
- cheap
- useful for broad triage

But it is not yet strong enough to be the main decision engine for:

- business potential
- target customer clarity
- hosted-gap detection
- market timing
- commercial readiness
- founder-grade opportunity ranking

So the best next move is not “make everything fancier at once.” It is:

- strengthen Analyst into a real evidence-backed opportunity analyst

---

## 1. Analyst Vision

### Current Analyst

Current Analyst behavior is effectively:

- fetch README
- normalize README
- apply heuristic business analysis
- persist result

This is good for:

- low-cost first pass
- bulk processing
- deterministic fallback

This is weak for:

- incomplete repos
- inaccurate READMEs
- repos with weak docs but strong code
- repos with strong marketing language but weak implementation
- repos where the real signal is in tests, issues, releases, commit patterns, package structure, or deployment hints

### Target Analyst

The target Analyst should become a two-stage system:

1. `Analyst Extractor`
   Deterministic evidence extraction
2. `Analyst Reasoner`
   Heuristic reasoning and/or LLM-powered reasoning over the extracted evidence

This gives the project:

- stronger precision
- better explainability
- better trust
- better handling of missing READMEs
- better readiness for later multi-repo synthesis

---

## 2. Target Analyst Architecture

### Stage A: Evidence Extraction

This stage should produce structured facts, not opinions.

Examples:

- `has_readme`
- `readme_length`
- `has_tests`
- `has_ci`
- `has_releases`
- `has_license`
- `has_docs_dir`
- `has_examples_dir`
- `has_deploy_config`
- `has_containerization`
- `has_auth_signals`
- `has_billing_signals`
- `has_team_workflow_signals`
- `has_api_signals`
- `has_admin_panel_signals`
- `has_plugin_architecture_signals`
- `primary_languages`
- `dependency_footprint`
- `recent_commit_count_30d`
- `recent_commit_count_90d`
- `contributors_count`
- `stars`
- `forks`
- `open_issues`
- `release_recency`
- `issue_velocity`
- `homepage_present`
- `pricing_url_present`
- `cloud_or_hosted_mentions`
- `enterprise_feature_mentions`
- `security_or_compliance_mentions`

This stage should be deterministic and cheap.

### Stage B: Reasoning

This stage should consume:

- README evidence
- extracted repo evidence
- GitHub metadata
- community/activity indicators
- optionally issue/pr discussion summaries

It should produce structured judgments such as:

- `problem_statement`
- `target_customer`
- `target_team_size`
- `product_type`
- `business_model_guess`
- `commercial_readiness`
- `technical_maturity`
- `hosted_gap_strength`
- `market_timing`
- `competitive_density`
- `monetization_potential`
- `risks`
- `limitations`
- `recommended_action`
- `confidence`

The key rule:

- reasoning must be evidence-backed, not README-poetry

---

## 3. Analyst Modes

The best design is not “heuristics or LLM.”
It is “fast path plus deep path.”

### Mode 1: Fast Analyst

Purpose:

- process large backlogs cheaply
- rank repos roughly
- provide broad pipeline coverage

Inputs:

- README
- metadata
- extracted deterministic signals

Outputs:

- tags
- category
- rough fit score
- rough hosted-gap score
- confidence estimate
- shortlist recommendation

Properties:

- cheap
- fast
- deterministic or mostly deterministic
- moderate precision

### Mode 2: Deep Analyst

Purpose:

- analyze shortlisted repos deeply
- generate founder-grade reasoning
- improve opportunity quality

Inputs:

- full evidence pack
- README
- extracted structured repo facts
- selected code/file summaries
- issue/release/community signals
- category context
- optionally similar-repo context

Outputs:

- full opportunity memo
- structured business scores
- confidence
- contradiction flags
- evidence citations
- recommended next action

Properties:

- slower
- more expensive
- much higher value

### Recommendation

Use both:

- `Fast Analyst` on broad intake
- `Deep Analyst` only on:
  - operator-selected repos
  - high-score shortlist repos
  - family candidates
  - strategic categories of interest

---

## 4. Evidence Model the Analyst Needs

### 4.1 README Evidence

Current README analysis is useful, but incomplete.

What to extract:

- product description
- installation path
- deployment guidance
- local vs hosted assumptions
- references to teams, orgs, admins, workflows
- references to integrations, APIs, plugins
- references to pricing, licensing, editions
- references to roadmap or maturity
- references to analytics/reporting/admin features

### 4.2 Codebase Evidence

The system should inspect the repository structure and selected files for:

- test directories and frameworks
- CI config
- release workflows
- package manifests
- infra/deployment files
- auth patterns
- API/server presence
- frontend/admin panel presence
- plugin/module patterns
- multi-tenant/team concepts
- enterprise/security hints

### 4.3 Community / Activity Evidence

Collect signals such as:

- stars
- forks
- contributors
- release cadence
- last commit
- recent commit frequency
- issue freshness
- issue/PR responsiveness
- star acceleration if available

### 4.4 Commercial Evidence

Detect:

- hosted version exists or not
- team workflows implied or explicit
- admin features implied or explicit
- operational pain to self-host
- monetizable “missing layer” features
- whether the repo is likely hobbyware, internal tooling, or productizable OSS

---

## 5. Analyst Output Contract

The Analyst should not return only prose.

It should return:

### Structured fields

- `category`
- `agent_tags`
- `problem_statement`
- `target_customer`
- `product_type`
- `business_model_guess`
- `monetization_potential`
- `technical_maturity_score`
- `commercial_readiness_score`
- `hosted_gap_score`
- `market_timing_score`
- `confidence_score`
- `recommended_action`

### Evidence fields

- `evidence_summary`
- `contradictions`
- `missing_information`
- `red_flags`
- `supporting_signals`

### Short human memo

- concise but evidence-backed
- not generic hype

---

## 6. Analyst Scoring System

The project needs a more explicit scoring framework.

Recommended dimensions:

1. `Business Potential`
   Is there a plausible commercial opportunity here?

2. `Hosted Gap`
   Does OSS exist but hosted/commercial execution look weak or missing?

3. `Technical Maturity`
   Is the repo credible enough to build upon?

4. `Commercial Readiness`
   Does it already resemble a product, not just code?

5. `Market Timing`
   Are there signs that this category is becoming more important now?

6. `Differentiation`
   Is the opportunity meaningfully distinct from existing vendors?

7. `Trust / Risk`
   Is this repo low-risk enough to consider seriously?

8. `Confidence`
   How trustworthy is the current judgment based on the evidence available?

Each score should be:

- explicit
- documented
- explainable
- evidence-backed

---

## 7. Analyst Contradiction Engine

This is one of the highest-value missing pieces.

The system should explicitly detect mismatches like:

- README claims enterprise readiness but no tests or release discipline exist
- README implies team workflows but no auth/admin surface is visible
- strong marketing language but no recent activity
- large stars but weak contributor depth
- “production ready” wording with minimal operational evidence

This should produce:

- `claim/evidence mismatch`
- `confidence reduction`
- possible downgrade in ranking

Without this, README-heavy analysis will often overrate weak repos.

---

## 8. Missing README Handling

This is now a critical product requirement.

A missing README should not create operational chaos.

Recommended handling:

- no auto-pause for missing README
- mark repo analysis as incomplete or failed-with-known-reason
- extract partial evidence from repo metadata and code structure
- optionally send such repos into a lighter fallback analyzer
- lower confidence, not necessarily total discard

Possible statuses:

- `completed`
- `completed_low_confidence`
- `insufficient_evidence`
- `failed_operationally`

Today too many meaningfully different cases collapse into `failed`.

---

## 9. LLM Deep Analyst Design

### When to use LLM

Use LLM for:

- deep repo opportunity analysis
- nuanced business reasoning
- contradiction review
- founder memo generation
- comparative reasoning
- opportunity framing

Do not use LLM for:

- basic signal extraction
- simple directory scanning
- counting tests
- parsing deterministic metadata

### Input to LLM

The LLM should receive a compact evidence pack:

- repo metadata
- extracted structured evidence
- README summary or excerpt
- selected file evidence
- activity/community summary
- category context
- maybe similar repo hints

### Prompt areas

Have the LLM answer:

- What problem does this project solve?
- Who is the likely target customer or team?
- What evidence supports that?
- Is there a plausible business model?
- Is there a hosted / managed / enterprise gap?
- What signs indicate commercial readiness?
- What are the strongest red flags?
- What evidence is missing?
- How confident should we be?
- What should the operator do next?

### Output requirements

LLM output must be:

- structured JSON first
- short memo second
- confidence-tagged
- explicitly grounded in evidence

---

## 10. Analyst UI / Product Improvements

To make Analyst founder-grade, the UI should expose:

### In Repository Detail

- evidence score breakdown
- confidence meter
- contradiction warnings
- hosted-gap explanation
- “why this might be interesting”
- “why this might be misleading”
- evidence sources per conclusion

### In Repositories Catalog

- fast analyst score
- deep analyst score
- confidence
- hosted gap
- category
- agent tags
- shortlist flag

### In Overview / Control

- analyst throughput
- analyst coverage
- average confidence
- top failure reasons
- low-confidence bucket
- shortlisted candidate count

---

## 11. Analyst Data Model Additions

Recommended additions over time:

- `analysis_confidence_score`
- `analysis_mode` (`fast`, `deep`)
- `analysis_evidence_version`
- `analysis_contradictions_json`
- `analysis_signals_json`
- `hosted_gap_score`
- `technical_maturity_score`
- `commercial_readiness_score`
- `market_timing_score`
- `differentiation_score`
- `insufficient_evidence_reason`
- `analysis_summary_short`
- `analysis_summary_long`

Also store evidence snapshots so future model reruns remain auditable.

---

## 12. Analyst Roadmap by Phase

### Phase A: Stabilize Current Analyst

Goals:

- no operational pause cascades on missing README
- clearer analysis statuses
- confidence tracking
- better event severity hygiene

Deliverables:

- missing README becomes non-blocking
- `insufficient evidence` path
- clear low-confidence handling
- improved analyst incident semantics

### Phase B: Add Structured Extractor

Goals:

- deterministic repo facts
- repo structure evidence
- activity evidence

Deliverables:

- evidence extraction stage
- stored structured signal payload
- signal-based scoring inputs

### Phase C: Add Deep Analyst

Goals:

- high-quality opportunity reasoning
- evidence-backed business assessment

Deliverables:

- LLM-powered deep analysis path
- JSON output contract
- confidence score
- contradiction detection

### Phase D: Add Shortlist Engine

Goals:

- reduce operator noise
- surface best opportunities first

Deliverables:

- shortlist scoring
- “analyze deeper” queue
- operator action recommendations

### Phase E: Add Learning Loop

Goals:

- personalize intelligence to founder taste

Deliverables:

- learn from stars
- learn from user tags
- learn from accepted/rejected opportunities
- tune future ranking

---

## 13. Analyst Success Metrics

Measure:

- percent of repos with usable evidence
- percent of repos with deep analysis
- false-positive rate on high-fit repos
- operator agreement with top recommendations
- percent of high-confidence repos later starred/tagged/promoted
- number of meaningful opportunity candidates surfaced per 1000 repos
- analyst failure rate by type
- incidence of claim/evidence mismatch

---

## Part II: Full-System Roadmap

## 14. System Vision

The full project should become:

- a repository discovery system
- a product opportunity intelligence engine
- a founder decision-support system
- a family/market synthesis engine

Not just:

- an agent dashboard
- a repo browser
- a pipeline monitor

---

## 15. Target Layered Architecture

### Layer 1: Intake

Owned by:

- Firehose
- Backfill

Purpose:

- gather candidate repos
- preserve provenance
- maintain timeline truth

Enhancements needed:

- stronger provenance (`new`, `trending`, `backfill_window`)
- trend velocity signals
- star growth tracking
- ingestion source confidence

### Layer 2: Sanitation / Rule Filtering

Owned by:

- Bouncer

Purpose:

- remove junk
- remove spam
- remove cracked software / obvious abuse / homework noise
- keep Analyst focused on serious candidates

Enhancements needed:

- stronger rule system
- reputation/junk heuristics
- blocklist categories
- allowlist themes
- explicit rule explainability

### Layer 3: Structured Evidence Extraction

Owned by:

- Analyst Extractor phase

Purpose:

- convert repo into facts

Enhancements needed:

- directory/file scanning
- metadata extraction
- activity extraction
- commercial signal extraction

### Layer 4: Repo Reasoning

Owned by:

- Analyst Fast
- Analyst Deep

Purpose:

- decide whether repo is interesting and why

Enhancements needed:

- evidence-backed scoring
- hosted gap detection
- contradiction engine
- confidence

### Layer 5: Cross-Repo Synthesis

Owned by:

- Combiner

Purpose:

- compare related repos
- build families
- synthesize multi-repo opportunities

Enhancements needed:

- cluster by problem space
- compare OSS alternatives
- detect family-level white space
- produce venture-style opportunity briefs

### Layer 6: Strategic Memory and Operator Learning

Owned by:

- Obsession
- Overlord

Purpose:

- remember what the founder cares about
- remember patterns across sessions
- maintain taste, strategy, and active themes

Enhancements needed:

- preference learning
- thesis tracking
- active obsession themes
- strategic reminders

---

## 16. Agent-by-Agent Recommendations

### Firehose

Current role:

- live repo discovery

Recommended improvements:

- store more feed-specific provenance
- star-growth snapshots
- trend deltas
- duplicate overlap visibility
- early junk scoring hints

Firehose should answer:

- why did this repo appear now?
- was it new, trending, or both?
- how fast is it moving?

### Backfill

Current role:

- historical discovery windows

Recommended improvements:

- better timeline controls
- historical segment labeling
- backfill quality metrics
- discovery density per window
- historical emergence patterns

Backfill should answer:

- when did this category really start becoming active?
- which older repos still matter?

### Bouncer

Current role:

- triage rules

Recommended improvements:

- allow keywords
- block keywords
- reputation filter
- junkware/crackware suppression
- tutorial/homework suppression
- category-aware triage rules

Bouncer should answer:

- why was this repo allowed or blocked?
- which rule did it trigger?

### Analyst

Current role:

- README heuristic analysis

Recommended improvements:

- all items in Part I

### Combiner

Current role:

- idea synthesis

Recommended improvements:

- family-level synthesis
- competitor/alternative comparison
- hosted-gap aggregation
- “best wedge” suggestion
- idea portfolio generation
- adjacent market expansion suggestions

Combiner should answer:

- what is the strongest opportunity built from this family?
- should we combine these three repos into one product concept?

### Obsession

Current role:

- context tracking

Recommended improvements:

- thesis memory
- user taste memory
- watchlists
- long-term market themes
- recurring signals

Obsession should answer:

- what am I repeatedly attracted to?
- what category am I increasingly bullish on?

### Overlord

Current role:

- control plane / monitor

Recommended improvements:

- portfolio-level intelligence
- category health
- active bottlenecks
- strategy reminders
- shortlist health
- system trust metrics

Overlord should answer:

- where should the operator spend attention right now?
- what is decaying in system quality?

---

## 17. Founder-Grade Missing Features

These are the highest-value system-level additions.

### A. Shortlist Engine

You need:

- top 10 repos worth looking at now
- top 10 repos worth deep analysis
- top 10 candidate hosted-gap opportunities

### B. Family Graph

You need:

- repo families
- adjacent families
- substitute maps
- whitespace maps

### C. Hosted Gap Engine

This should become first-class.

Questions:

- is there open source adoption?
- is the self-hosting burden high?
- are team/enterprise needs visible?
- is there room for a managed product?

### D. Opportunity Comparison Engine

You need side-by-side comparison:

- repo A vs B vs C
- maturity
- market
- timing
- commercial gap

### E. Learning System

Operator actions should teach the system.

Signals:

- starred
- tagged
- promoted to family
- ignored
- rejected
- manually prioritized

### F. Confidence and Trust Layer

Every important output should answer:

- how confident are we?
- what evidence supports this?
- what evidence is missing?

---

## 18. Recommended Implementation Order

### Priority 1

- stabilize Analyst failure semantics
- add structured evidence extraction
- add confidence and contradiction support

### Priority 2

- add LLM deep analyst
- add shortlist engine
- improve Bouncer junk suppression

### Priority 3

- improve Combiner family synthesis
- add hosted-gap engine
- add opportunity comparison engine

### Priority 4

- add learning from operator behavior
- add obsession-driven thesis memory
- add portfolio-level Overlord intelligence

---

## 19. What “God-Like” Looks Like

The final system should be able to do all of this:

- ingest thousands of repos
- suppress junk automatically
- rank the top real candidates
- explain why a repo matters
- show confidence
- identify hosted/commercial gaps
- compare alternatives
- cluster families
- synthesize multi-repo product opportunities
- remember founder preferences
- improve over time

And eventually answer founder questions like:

- “What are the three most promising workflow OSS repos from the last 90 days?”
- “Which analytics repos look like hosted-gap opportunities?”
- “Which repo families are heating up but not yet commercially saturated?”
- “Compare these five repos and tell me which one has the best path to a product.”
- “Take these three repos and propose one superior combined product direction.”

That is the real target state.

---

## 20. Final Recommendation

If only one thing is upgraded next, upgrade Analyst.

The best single next move is:

- `Analyst Extractor + Analyst Deep`

Because that improves:

- intelligence quality
- shortlist quality
- Combiner inputs
- founder trust
- overall product value

Everything else becomes more useful once Analyst becomes evidence-backed and confidence-aware.

