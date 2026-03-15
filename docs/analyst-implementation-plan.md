# Analyst Enhancement Implementation Plan

## Purpose

This document turns the current analyst roadmap and the newer ideas into a repo-grounded implementation plan that fits the codebase as it exists today.

It is intentionally opinionated:

- replace the current heuristic README analyzer
- keep the current worker/job/artifact pattern
- add deterministic evidence before relying on deeper LLM reasoning
- separate "repo intelligence" from later "maintainer intelligence"

## Current State In This Repository

The current analyst path is simple and local:

1. `workers/agentic_workers/jobs/analyst_job.py`
   - loads accepted repositories
   - fetches README via `GitHubFirehoseProvider.get_readme()`
   - normalizes README
   - calls `HeuristicReadmeAnalysisProvider`
   - validates JSON with `ReadmeBusinessAnalysis`
   - persists results and artifacts

2. `workers/agentic_workers/providers/readme_analyst.py`
   - contains `HeuristicReadmeAnalysisProvider`
   - performs keyword matching only
   - returns a very small schema:
     - `monetization_potential`
     - `category`
     - `agent_tags`
     - `pros`
     - `cons`
     - `missing_feature_signals`

3. `workers/agentic_workers/storage/analysis_store.py`
   - stores one `RepositoryAnalysisResult`
   - writes README and analysis artifacts
   - keeps source metadata in JSON

4. `backend/app/schemas/repository_exploration.py`
   - exposes the same small contract to the API/UI

5. `frontend/src/components/repositories/RepositoryDetailClient.tsx`
   - assumes analyst output is mostly:
     - fit
     - category
     - pros/cons
     - raw analysis artifact JSON

Important operational note:

- missing README is already treated as non-blocking for pause policy, but it still collapses into `analysis_status=failed`
- `analysis_status` currently mixes lifecycle and semantic outcome
- analyst run tracking already supports `provider_name`, `model_name`, and token counts through the shared agent-run system
- the repo already has one existing LLM pattern in `workers/agentic_workers/providers/combiner_provider.py`
- categories already exist as a backend enum, but they are only weakly populated because the current analyst is too shallow
- analyst-generated tags already exist as `agent_tags`, but there is no strong taxonomy strategy behind them yet

## What To Keep, Replace, And Defer

### Keep

- `normalize_readme()` as a preprocessing step
- `run_analyst_job()` as the orchestration entry point
- artifact-first persistence
- backend repository detail/catalog surfaces
- worker eventing, pause policy, and run tracking
- a fast-path analyst mode for broad backlog coverage

### Replace

- `HeuristicReadmeAnalysisProvider`
- the current tiny analysis schema as the only analyst contract
- README-only reasoning as the primary decision engine
- unstable category/tag generation without taxonomy controls

### Defer Or Re-scope

These ideas are good, but should not be in the first analyst rewrite:

1. "Read the whole codebase"
   - not scalable for broad intake
   - replace with selective evidence extraction from top-level tree, manifests, CI files, docs, and a few representative files

2. "Map the humans behind the code"
   - valuable, but it is a separate enrichment layer
   - requires contributor endpoints, GitHub user profile lookups, PR merge analysis, and likely new privacy/reliability guardrails
   - should be a later `MaintainerIntel` phase, not analyst v1

3. "Draft an email to maintainers"
   - this is downstream action generation
   - should only exist after maintainer intelligence is stable and operator-approved

## Product Decision

The right target is not "heuristics or LLM."

The right target is:

1. `Fast Analyst`
   - deterministic evidence extraction
   - optional small LLM README interpretation
   - cheap and broad

2. `Deep Analyst`
   - LLM reasoning over a structured evidence pack
   - only for shortlisted or operator-selected repositories

This means the initial delivery should be split:

- Phase 1 ships a drop-in `LLMReadmeAnalysisProvider` to replace the toy heuristic provider
- Phase 2 adds a deterministic evidence extractor
- Phase 3 adds a deeper evidence-backed reasoner

## Recommended Target Architecture

### Taxonomy Layer: Categories And Tags

This needs to become a first-class part of the analyst design.

Right now the website already expects:

- one primary `category`
- zero or more `agent_tags`
- zero or more `user_tags`

The missing piece is taxonomy quality.

The analyst should own:

1. `Primary category`
   - one canonical category per repository for catalog grouping and filtering

2. `Secondary tags`
   - multiple analyst-generated tags for richer search, clustering, and later synthesis

3. `Confidence`
   - category/tag assignment should carry confidence, not just a raw label

4. `Unknown / needs review`
   - the system must be allowed to say "unclear" instead of hallucinating a bad category

### Category Strategy

Do not let the model invent arbitrary new categories during normal analysis.

That would make the catalog noisy and unstable. Instead use:

- a controlled primary category vocabulary
- a more flexible analyst tag vocabulary
- a separate taxonomy review path for adding new categories

### Current Primary Categories In The Codebase

The current enum-backed categories are:

- `workflow`
- `analytics`
- `devops`
- `infrastructure`
- `devtools`
- `crm`
- `communication`
- `support`
- `observability`
- `low_code`
- `security`
- `ai_ml`
- `data`
- `productivity`

This is a decent starting point, but it is not complete enough for long-term use.

### Recommended Category Evolution

Keep the primary category list small and stable.

A reasonable next controlled set would be:

- `ai_ml`
- `analytics`
- `automation`
- `communication`
- `crm`
- `data`
- `developer_platform`
- `devops`
- `documentation`
- `ecommerce`
- `education`
- `fintech`
- `infrastructure`
- `knowledge_management`
- `low_code`
- `marketplace`
- `observability`
- `productivity`
- `security`
- `support`
- `workflow`

Important rule:

- primary categories should describe the business or product domain
- they should not be overly specific implementation labels

### Tag Strategy

Analyst tags should be more expressive than categories, but still guided.

Recommended agent tag groups:

- buyer tags:
  - `b2b`
  - `b2c`
  - `developer`
  - `internal-tools`
  - `enterprise`
  - `smb`

- product-shape tags:
  - `api`
  - `platform`
  - `saas-candidate`
  - `self-hosted`
  - `open-core-candidate`
  - `marketplace`
  - `plugin-ecosystem`

- capability tags:
  - `automation`
  - `reporting`
  - `auth`
  - `billing`
  - `admin-panel`
  - `multi-tenant`
  - `integrations`
  - `workflow`
  - `notifications`
  - `analytics`

- technical tags:
  - `python`
  - `typescript`
  - `go`
  - `docker`
  - `kubernetes`
  - `postgres`
  - `react`
  - `nextjs`

- opportunity tags:
  - `hosted-gap`
  - `commercial-ready`
  - `needs-deep-analysis`
  - `low-confidence`
  - `maintainer-risk`

### Taxonomy Decision

Use a hybrid strategy:

1. primary category:
   - strict controlled vocabulary

2. analyst tags:
   - semi-controlled vocabulary with periodic expansion

3. free-form suggestions:
   - model may propose candidate new tags/categories in a separate review field
   - they do not go directly into the canonical catalog filters

This gives you accuracy without freezing the taxonomy forever.

### Layer A: Evidence Extraction

Add a deterministic extractor that produces facts, not opinions.

Minimum first-pass signals:

- README:
  - `has_readme`
  - `readme_length`
  - `readme_mentions_hosted`
  - `readme_mentions_cloud`
  - `readme_mentions_enterprise`
  - `readme_mentions_pricing`
  - `readme_mentions_auth`
  - `readme_mentions_api`
  - `readme_mentions_plugin`
  - `readme_mentions_team`

- Repo metadata:
  - `stars`
  - `forks`
  - `github_created_at`
  - `pushed_at`
  - `days_since_last_push`

- File structure and manifests:
  - `has_tests`
  - `has_ci`
  - `has_releases_config`
  - `has_license`
  - `has_docs_dir`
  - `has_examples_dir`
  - `has_dockerfile`
  - `has_containerization`
  - `has_deploy_config`
  - `has_backend_surface`
  - `has_frontend_surface`
  - `has_admin_surface`
  - `has_auth_signals`
  - `has_api_surface`
  - `primary_languages`
  - `package_managers`
  - `framework_signals`

- GitHub activity:
  - `contributors_count`
  - `recent_commit_count_30d`
  - `recent_commit_count_90d`
  - `open_issues`
  - `release_count`
  - `last_release_at`
  - `pr_merge_rate_recent`
  - `issue_response_time_estimate`

### Layer B: Fast Reasoning

Use either deterministic scoring or a small LLM call to produce:

- `category`
- `category_confidence_score`
- `agent_tags`
- `agent_tag_confidence`
- `suggested_new_categories`
- `suggested_new_tags`
- `problem_statement`
- `target_customer`
- `product_type`
- `business_model_guess`
- `monetization_potential`
- `technical_maturity_score`
- `commercial_readiness_score`
- `hosted_gap_score`
- `confidence_score`
- `recommended_action`

### Layer C: Deep Reasoning

For shortlisted repos only, feed the LLM:

- repo metadata
- deterministic signals
- README summary/excerpt
- selected file evidence
- activity summary
- contradiction candidates

Deep output should add:

- `market_timing_score`
- `differentiation_score`
- `trust_risk_score`
- `contradictions`
- `supporting_signals`
- `red_flags`
- `missing_information`
- `analysis_summary_short`
- `analysis_summary_long`

## Contract Recommendation

Do not overload `RepositoryIntake.analysis_status`.

That field currently behaves like lifecycle state:

- `pending`
- `in_progress`
- `completed`
- `failed`

The roadmap's semantic outcomes are different. Introduce separate fields for them.

### Keep

- `analysis_status` for lifecycle

### Add

- `analysis_mode`: `fast`, `deep`
- `analysis_outcome`: `completed`, `completed_low_confidence`, `insufficient_evidence`, `failed_operationally`
- `analysis_confidence_score`: integer 0-100
- `category_confidence_score`
- `analysis_provider_name`
- `analysis_model_name`
- `analysis_evidence_version`
- `analysis_schema_version`
- `insufficient_evidence_reason`

This preserves current API semantics and avoids breaking every place that already treats `analysis_status` as pipeline state.

## Proposed Data Model Changes

### Extend `RepositoryAnalysisResult`

Add fields such as:

- `analysis_mode`
- `analysis_outcome`
- `category_confidence_score`
- `problem_statement`
- `target_customer`
- `product_type`
- `business_model_guess`
- `recommended_action`
- `analysis_confidence_score`
- `technical_maturity_score`
- `commercial_readiness_score`
- `hosted_gap_score`
- `market_timing_score`
- `differentiation_score`
- `trust_risk_score`
- `evidence_summary`
- `analysis_summary_short`
- `analysis_summary_long`
- `supporting_signals`
- `red_flags`
- `missing_information`
- `contradictions`
- `analysis_signals_json`
- `analysis_scores_json`
- `suggested_new_categories`
- `suggested_new_tags`
- `analysis_provider_name`
- `analysis_model_name`
- `input_tokens`
- `output_tokens`
- `total_tokens`

### Taxonomy Tables Or Config

For long-term quality, move category and agent-tag definitions out of scattered code constants.

Recommended options:

1. first step:
   - keep category enum for primary category
   - add central Python constants for allowed agent tags

2. later step:
   - add taxonomy tables such as:
     - `analysis_category_definition`
     - `analysis_tag_definition`
     - `analysis_taxonomy_suggestion`

This allows the analyst to suggest new taxonomy entries without immediately polluting the production filter set.

### Add Evidence Artifact Types

Current artifacts:

- README snapshot
- analysis result

Recommended additions:

- `analysis_evidence`
- `analysis_selected_files` (optional)

The evidence artifact should contain the exact structured pack sent to the deep reasoner.

## GitHub Provider Expansion

`workers/agentic_workers/providers/github_provider.py` is currently too narrow for the target analyst.

Add read-only enrichment methods such as:

- `get_repository_metadata()`
- `list_contributors(limit=5)`
- `list_releases(limit=10)`
- `list_recent_commits(limit=100)`
- `list_recent_pull_requests(limit=50)`
- `list_recent_issues(limit=50)`
- `get_repository_tree(depth_limit=2)` or equivalent selective file listing
- `get_file_contents(path)` for a small allowlist only

Important constraint:

- do not fetch arbitrary full codebases during broad intake
- use an allowlist of evidence files:
  - `package.json`
  - `pyproject.toml`
  - `requirements.txt`
  - `Dockerfile`
  - `.github/workflows/*`
  - `docker-compose.yml`
  - `README*`
  - `docs/*`
  - top-level `src/`, `app/`, `server/`, `web/`, `api/`, `tests/` presence only

## Maintainer Intelligence: Separate Phase

The "god-like state" idea is directionally correct but should be split out.

### Do not bundle into the first analyst rewrite

Reason:

- different data shape
- different privacy/accuracy risks
- materially larger GitHub API cost
- higher false-positive risk around employment/open-to-work inference

### Add later as a distinct enrichment module

Suggested name:

- `MaintainerIntelProvider`

Suggested outputs:

- top contributors
- maintainer concentration risk
- recent merge responsiveness
- maintainer activity freshness
- profile availability
- confidence of inference

Hard rule:

- only use explicit GitHub-visible signals first
- do not infer employment changes from weak hints

## LLM Strategy

### Phase 1 Requirement

Replace `HeuristicReadmeAnalysisProvider` with `LLMReadmeAnalysisProvider`.

That provider should:

- accept normalized README plus basic repo metadata
- request strict JSON
- validate with Pydantic
- return no free-form prose outside the JSON contract
- track provider/model/tokens in the persisted record and agent run

### Phase 2 Requirement

Add `LLMRepositoryAnalysisProvider` or `LLMAnalystReasoner`.

That provider should consume the structured evidence pack, not raw README only.

### JSON Contract For The First LLM Provider

The first provider can start with:

- `target_audience`
- `technical_stack`
- `open_problems`
- `competitors`
- `problem_statement`
- `target_customer`
- `product_type`
- `business_model_guess`
- `category`
- `category_confidence_score`
- `agent_tags`
- `suggested_new_categories`
- `suggested_new_tags`
- `monetization_potential`
- `pros`
- `cons`
- `missing_feature_signals`
- `confidence_score`
- `recommended_action`

This keeps the initial migration manageable while materially improving quality over keyword counting.

## Model Recommendation

### Best Default Recommendation

Use a small hosted model first, not an open-source model.

Recommended order:

1. `Claude 3.5 Haiku`
2. `Gemini 2.5 Flash` or the current Flash-tier model you have available
3. `GPT-5 mini` or the current OpenAI small reasoning-capable API model

### Why Claude 3.5 Haiku Is The Best Initial Fit Here

- the repo already depends on `anthropic`
- Combiner already uses Anthropic patterns
- smallest integration delta
- good structured output reliability
- easy reuse of provider/model/token tracking conventions already present in Combiner

### Why Gemini Flash Is Still A Strong Option

- usually strong price/latency for extraction-style tasks
- good candidate if broad analyst throughput becomes the main bottleneck
- better choice if you want high-volume fast-path analysis and are comfortable adding a new provider integration

### When To Consider OpenAI

- if you want one vendor for both fast and deep analyst reasoning later
- if you already plan wider OpenAI usage elsewhere in the product
- if structured outputs and eval tooling become central to the workflow

### When To Consider Open Source

Only use an open-source model for analyst v1 if one of these is true:

- you must run locally
- privacy rules require no hosted LLM
- you already operate local inference infrastructure

Otherwise it is the wrong optimization right now.

### Open-Source Recommendation

If you must go open-source, prefer a small instruct model that is strong at JSON extraction over a large general model that is expensive to host.

Candidates to evaluate:

- Qwen instruct family
- Mistral Small family
- Llama Instruct family

But for this project today, hosted small-model inference is the pragmatic choice.

## Recommended Delivery Phases

### Phase 1: Replace The Toy Provider

Goal:

- stop using keyword counting

Deliverables:

- `LLMReadmeAnalysisProvider`
- strict Pydantic schema
- provider/model/token tracking in analyst runs
- config for selecting analyst provider
- tests for valid JSON, invalid JSON, timeout, and rate limit paths

Files expected to change:

- `workers/agentic_workers/providers/readme_analyst.py`
- `workers/agentic_workers/jobs/analyst_job.py`
- `workers/agentic_workers/main.py`
- `workers/agentic_workers/core/config.py`
- `.env.example`
- worker tests
- `backend/app/models/repository.py` if category fields are extended immediately
- backend migration files if taxonomy fields are persisted in phase 1

### Phase 2: Add Deterministic Evidence Extraction

Goal:

- give the analyst facts beyond the README

Deliverables:

- `RepositoryEvidenceExtractor`
- GitHub provider expansion
- evidence artifact persistence
- stored `analysis_signals_json`
- deterministic category/tag hints from repo structure and ecosystem signals

Files expected to change:

- `workers/agentic_workers/providers/github_provider.py`
- new extractor module under `workers/agentic_workers/providers/` or `workers/agentic_workers/pipelines/`
- `workers/agentic_workers/storage/analysis_store.py`
- backend models and migrations
- backend schemas/services

### Phase 3: Add Fast Analyst Scores And Contradictions

Goal:

- produce evidence-backed scoring even before deep analysis

Deliverables:

- explicit score calculation
- contradiction engine
- confidence model
- `analysis_outcome` support

### Phase 4: Add Deep Analyst

Goal:

- founder-grade analysis for top candidates

Deliverables:

- deep evidence pack
- deep LLM reasoning path
- detailed summaries
- recommendation quality upgrade

### Phase 5: Add Maintainer Intelligence

Goal:

- map the humans behind the repo without destabilizing the base analyst

Deliverables:

- contributor enrichment
- maintainer responsiveness
- concentration risk
- optional founder outreach drafting

## Backend And UI Changes

### Backend

Update:

- `backend/app/models/repository.py`
- `backend/app/schemas/repository_exploration.py`
- `backend/app/repositories/repository_exploration_repository.py`
- `backend/app/services/repository_exploration_service.py`
- repository API integration tests

Expose new fields gradually:

- confidence
- hosted gap
- maturity
- readiness
- contradictions
- evidence summary
- analysis mode/outcome
- category confidence
- richer analyst tags
- suggested taxonomy entries for operator review

### Frontend

Repository detail should eventually show:

- score breakdown
- confidence
- contradictions
- supporting signals
- red flags
- evidence sources

Catalog should eventually show:

- fast/deep mode indicator
- confidence
- hosted-gap score
- shortlist-ready state
- better category coverage
- analyst tag filtering that is actually meaningful

Do not block the backend rollout on the full UI. It is fine to expose the new JSON in detail view first.

## Testing Plan

### Worker tests

Add tests for:

- valid LLM JSON success
- invalid JSON schema rejection
- missing required keys
- timeout handling
- rate limit handling
- token usage persistence
- missing README -> low confidence or insufficient evidence path
- contradiction generation with synthetic evidence
- category assignment from controlled vocabulary
- tag assignment from controlled vocabulary
- suggestion handling for unknown category/tag candidates

### Backend tests

Add tests for:

- new analysis fields serialized in detail route
- catalog filtering/sorting on new scores or modes
- backward compatibility when old rows lack new fields
- category display and filtering with expanded taxonomy support
- analyst tag serialization and filtering

### Frontend tests

Add tests for:

- rendering confidence and contradictions
- rendering deep vs fast analyst results
- handling insufficient evidence gracefully

## Rollout Rules

### Rule 1

Do not remove the heuristic path until the LLM path has:

- schema validation
- retries
- provider/model/tokens recorded
- deterministic tests

### Rule 2

Do not make deep analysis the default for all accepted repos.

Keep deep analysis gated to:

- top scored repos
- operator-selected repos
- family candidates

### Rule 3

Do not treat missing README as an operational failure if evidence extraction still succeeds.

Prefer:

- lifecycle status: `completed`
- semantic outcome: `completed_low_confidence` or `insufficient_evidence`

## Concrete First Build Order

1. Add analyst provider config and model selection support.
2. Implement `LLMReadmeAnalysisProvider`.
3. Define controlled primary categories and controlled analyst tags.
4. Extend analysis schema with confidence, category, and tag fields.
5. Persist provider/model/token metadata for analyst.
6. Add a deterministic evidence extractor for repo structure and GitHub activity.
7. Store an evidence artifact and `analysis_signals_json`.
8. Add contradiction logic.
9. Add deep analyst mode.
10. Add maintainer intelligence as a separate phase.

## Final Recommendation

If only one thing is implemented now, do this:

- replace `HeuristicReadmeAnalysisProvider` with `LLMReadmeAnalysisProvider`
- immediately follow it with a deterministic evidence extractor

That combination fits the current codebase, raises intelligence quality fast, and creates the right foundation for later maintainer mapping, shortlist generation, and family synthesis.

## External References For Model Selection

- Anthropic models overview: https://docs.anthropic.com/en/docs/about-claude/models/overview
- Anthropic pricing: https://www.anthropic.com/pricing
- Google Gemini model docs: https://ai.google.dev/gemini-api/docs/models
- Google Gemini pricing: https://ai.google.dev/pricing
- OpenAI API pricing: https://openai.com/api/pricing/
- OpenAI API models overview: https://platform.openai.com/docs/models
- Mistral models: https://docs.mistral.ai/getting-started/models/
- Meta Llama models: https://www.llama.com/docs/model-cards-and-prompt-formats/
