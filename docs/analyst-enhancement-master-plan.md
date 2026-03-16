# Analyst Enhancement Master Plan

## Objective

Upgrade the Analyst from a mostly README-keyword classifier into a reliable repository intelligence engine that can:

- assign trustworthy `category` and `agent_tags`
- surface confidence that means something
- highlight monetizable opportunities without over-labeling
- preserve deterministic operation in `heuristic` mode
- support richer LLM-backed analysis when API-backed providers are enabled

This plan is grounded in the current codebase and local dataset, not a hypothetical redesign.

## Current Audit

Observed before this enhancement wave:

- The active heuristic provider ignored the evidence payload entirely.
- Most stored analyses were low confidence because heuristic output did not emit real confidence values.
- Tagging over-relied on naive substring matching, which caused false positives.
  - Example class of bug: `form` matching inside words like `platform`.
- Common emerging tags were being pushed into `suggested_new_tags` instead of the canonical vocabulary.
- Strategic opportunity tags could be drowned out by technology-stack tags.

## Target State

The Analyst should behave as a layered pipeline:

1. Deterministic evidence extraction
2. Evidence-aware classification
3. Confidence calibration
4. Taxonomy normalization
5. Opportunity-oriented tagging
6. Clear operator outcomes

## Enhancement Workstreams

### 1. Evidence-First Heuristic Analysis

The heuristic provider must consume:

- README content
- evidence summary
- score breakdown
- structured repository signals
- contradictions, red flags, and missing information

Expected result:

- heuristic mode stays local and cheap
- but stops behaving like a README-only keyword toy

### 2. Confidence That Reflects Reality

Confidence should be based on:

- category evidence strength
- README richness
- repository evidence richness
- contradictions and insufficiency
- signal consistency

Expected result:

- `completed` should mean high-confidence analysis
- `completed_low_confidence` should become the exception, not the default

### 3. Taxonomy Hardening

The controlled taxonomy should prefer:

- fewer generic tags
- stronger product/opportunity tags
- exact signal matching over substring drift

Immediate canonical tag additions:

- `forms`
- `gateway`
- `embedded`
- `migration`
- `approval`
- `ticketing`
- `lineage`

### 4. Opportunity-Oriented Output

The Analyst should explicitly surface:

- `commercial-ready`
- `hosted-gap`
- `saas-candidate`
- `needs-deep-analysis`
- `maintainer-risk`

These should outrank incidental stack tags when the final top tags are selected.

### 5. Reanalysis Strategy

Every material heuristic/taxonomy improvement should bump the analysis schema version so completed repositories are re-queued and refreshed automatically.

## Acceptance Criteria

The Analyst enhancement is considered successful when:

- heuristic mode consumes evidence instead of discarding it
- exact signal matching removes major substring false positives
- common tags move from `suggested_new_tags` into canonical tags where appropriate
- confidence fields are populated with meaningful values
- a healthy subset of repos can now reach `analysis_outcome = completed`
- improved schema version triggers reanalysis of older rows automatically

## Implemented In This Wave

This pass implements the highest-value upgrades now:

- Evidence-aware heuristic provider
- Real category and overall confidence scoring
- Exact signal matching utilities instead of naive substring-only matching
- Canonical tag expansion for the most common emerging tags
- Better strategic tag prioritization over raw stack tags
- Schema-version bump to force refresh of older completed analyses

## Files Changed In This Wave

- [readme_analyst.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/providers/readme_analyst.py)
- [repository_evidence.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/providers/repository_evidence.py)
- [analysis_store.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/storage/analysis_store.py)
- [test_llm_readme_analyst.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/tests/unit/test_llm_readme_analyst.py)

## Remaining Follow-Up Work

These are still valuable, but not blockers for this wave:

- shared review queue for low-confidence taxonomy corrections
- better Bouncer filtering for clearly non-product repositories
- optional LLM calibration pass for high-value candidates only
- catalog and operator views that expose taxonomy QA cohorts directly
- periodic Analyst quality reports over sampled repositories

## Manual Verification

1. Start the stack and let Analyst re-run against accepted repositories.
2. Open `/repositories` and inspect refreshed repository detail pages.
3. Confirm category confidence and overall confidence are no longer mostly zero.
4. Check that obvious false-positive tags like `forms` are reduced.
5. Confirm common tags such as `gateway`, `migration`, and `embedded` now appear as canonical tags rather than mostly suggestions.
6. Verify that some refreshed repositories now land in `analysis_outcome = completed` instead of almost everything being `completed_low_confidence`.

## Operator Note

Because the analysis schema version was bumped in this wave, previously completed analyses with the older schema will be treated as stale and reprocessed by Analyst.
