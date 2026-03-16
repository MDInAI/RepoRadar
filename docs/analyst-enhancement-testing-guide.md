# Analyst Enhancement Testing Guide

## Purpose

This guide explains:

- what changed in the Analyst implementation
- what you should expect in the website
- what is editable in the Control panel
- how to test the Analyst manually
- how category and tag assignment is supposed to behave
- what is still future work

Use this while testing the Analyst from the UI.

## Executive Summary

The Analyst is no longer a thin README-only step.

It now supports:

- evidence-backed analysis
- controlled provider selection
- controlled category assignment
- controlled agent-tag assignment
- richer confidence and score output
- clearer control-plane visibility
- automatic refresh of legacy completed analyses that are missing the new schema

The Control panel now has an editable Analyst section. If you do not see an editor and only see static information, that is a troubleshooting case and this guide explains exactly what to do.

## What The Analyst Actually Does

The Analyst currently works like this:

1. It selects repositories that are:
   - `accepted` by triage
   - not yet fully analyzed with the current schema

2. It marks the repository as `analysis in progress`.

3. It tries to fetch the repository README from GitHub.

4. It extracts deterministic evidence from what is available:
   - normalized README text
   - repository metadata
   - selected repository intelligence signals

5. It decides whether there is enough evidence to do normal analysis.

6. If there is enough evidence:
   - it runs the configured Analyst provider in `fast` mode
   - and, when the evidence says it is justified, it can escalate to `deep` mode

7. If there is not enough evidence:
   - it still completes analysis
   - but the semantic outcome becomes `insufficient_evidence`

8. It validates and persists:
   - primary category
   - category confidence
   - normalized `agent_tags`
   - suggested new categories/tags when the taxonomy does not fit cleanly
   - score breakdown
   - contradictions
   - missing information
   - provider/model provenance
   - evidence-backed summaries

9. It writes artifacts and updates the repository detail view.

So the Analyst is not just "ask an LLM about the README."

It is:

- evidence extraction
- controlled taxonomy assignment
- confidence-aware analysis
- persisted artifacts and metadata
- operator-visible output

## Analyst Pipeline In Plain English

If you want the exact mental model, the current Analyst pipeline is:

1. Pick accepted repositories whose analysis is missing, stale, failed, or still on the old schema.
2. Mark the repository as `in_progress`.
3. Try to fetch the GitHub README.
4. Normalize the README text if it exists.
5. Collect deterministic repository evidence such as:
   - metadata
   - tree paths
   - selected files
   - contributors
   - releases
   - recent commits
   - recent pull requests
   - recent issues
6. Compute evidence signals and score breakdowns such as:
   - activity
   - release maturity
   - hosted-gap potential
   - market timing
   - maintainer concentration risk
   - contradictions
   - missing information
7. Choose how analysis should proceed:
   - if evidence is too thin, finish as `insufficient_evidence`
   - otherwise run normal provider-backed analysis in `fast` mode
8. Optionally run `deep` mode if the repo looks strategically important enough.
9. Validate the result against the controlled taxonomy.
10. Persist the final analysis plus evidence-backed metadata.

That means the Analyst is currently a two-layer system:

- deterministic evidence extraction first
- provider interpretation second

The provider is no longer the whole analysis. It is only one stage inside the pipeline.

## Provider Modes

The editable Analyst provider modes mean:

### `heuristic`

- no external LLM call
- deterministic README-oriented rules only
- token usage stays `0`
- fastest and safest mode for offline or cheap batch operation

This mode still produces:

- primary `category`
- normalized `agent_tags`
- monetization guess
- pros/cons
- missing-feature signals

But it is weaker than the model-backed modes when the repo is subtle or ambiguous.

### `llm`

- Anthropic-backed provider
- better for nuanced category/tag judgment
- supports fast and deep passes
- can hit provider-side rate limits or key/config issues

### `gemini`

- Gemini-compatible provider
- same role as `llm`, but using Gemini-compatible configuration
- useful if you want a different model stack or endpoint

## When Fast Mode Becomes Deep Mode

The Analyst always starts with `fast` mode first.

It can escalate to `deep` mode when the repository looks important or strategically promising enough, for example when there is strong evidence of:

- high star count
- strong recent commit activity
- strong hosted-gap score
- strong market-timing score
- both frontend and backend surfaces with enough maintainer activity

So deep mode is not random and it is not always-on. It is a targeted second pass for stronger candidates.

## What Category And Tag Assignment Really Means

Yes. The Analyst is absolutely supposed to do both:

- assign one primary `category`
- assign zero or more normalized `agent_tags`

This is one of its main jobs.

The current design is intentionally strict:

- canonical categories come from a controlled list
- canonical tags come from a controlled list
- anything outside the vocabulary gets redirected into suggestion fields

That is the right design for a catalog product because it prevents taxonomy drift.

If the Analyst freely invented categories every run, the repository catalog would become inconsistent very quickly.

## How Rate Limiting Works Now

This is important.

There are now two different rate-limit behaviors:

### GitHub rate limit during Analyst README/evidence fetch

If Analyst hits a GitHub `429` while fetching README or repository intelligence:

- it does **not** keep plowing through the rest of the queue
- it stops the current Analyst run early
- the affected repository is put back into a retryable pending state
- the remaining repositories stay pending
- Analyst does **not** auto-pause for a GitHub-side limit
- you should wait for the retry window and then run Analyst again

This is intentional.

A GitHub rate limit is not a repository-quality problem. It is temporary upstream throttling, so the safest behavior is:

- stop early
- preserve the queue
- retry later

### LLM/provider rate limit during model-backed analysis

If Analyst hits a model-provider `429`:

- it is treated differently from a GitHub README fetch limit
- the failure is recorded as an LLM-side rate limit
- the policy may pause Analyst
- the operator may need to wait for the model-provider limit window and then resume Analyst

### Why this distinction matters

GitHub rate limits and LLM rate limits are different operational problems:

- GitHub `429` means "upstream GitHub quota is exhausted right now"
- LLM `429` means "your model provider is throttling model calls right now"

The recovery path is not identical, so the guide should treat them separately.

## What To Do When You See A Rate-Limit Alert

If the alert says GitHub rate limit in Analyst:

1. Do not assume the queue is lost.
2. The run should stop early and leave work pending.
3. Wait for the retry window shown in the alert.
4. Run Analyst again.

If the alert says Analyst is paused because of provider/model throttling:

1. Wait for the provider limit window.
2. Open `/control`
3. Resume Analyst
4. Run Analyst again

## What Retries And What Does Not

This is the current intended behavior:

- missing README:
  - should complete as `insufficient_evidence`
  - should not pause Analyst
- GitHub `429`:
  - current repository goes back to retryable pending state
  - run stops early
  - remaining pending repositories stay untouched
- LLM/provider `429`:
  - failure is recorded
  - pause policy may pause Analyst
  - operator may need to resume manually after the limit window
- real malformed payload / operational error:
  - repository may record a true failure
  - operator should inspect `/incidents`

## Is This The Best Current Analyst Behavior?

For the current architecture, yes, this is the most suitable default behavior:

- do not hallucinate taxonomy
- do not force a result when evidence is thin
- do not convert temporary upstream throttling into permanent repo failure
- stop early on GitHub quota exhaustion instead of burning the queue
- preserve operator control for model-provider pauses

The main thing that is still not ideal is prevention:

- today we recover much better from rate limits
- but we still could do more to avoid hitting them in the first place

## What Is Still Missing From The Rate-Limit Story

The current implementation is safer now, but not perfect.

The biggest future improvement would be a shared GitHub cooldown gate across all GitHub consumers.

That means:

- if one GitHub-backed worker hits a real `429`
- the system records the retry window centrally
- other GitHub-backed workers avoid immediately hitting the same wall

That would be better than letting each worker discover the same exhausted window independently.

Other good prevention ideas:

- stronger README/result caching so Analyst does fewer repeat GitHub fetches
- a dedicated Analyst per-run fetch budget
- explicit "next safe retry time" surfaced in the Control panel
- a shared GitHub quota status card in Overview/Control

## Practical Ways To Reduce GitHub Rate Limiting Right Now

If you want fewer GitHub limits in the current system, these are the best practical levers:

### 1. Lower GitHub request pressure

In Control, reduce:

- `GITHUB_REQUESTS_PER_MINUTE`

This is the safest immediate knob when the system is hitting GitHub too aggressively.

### 2. Increase pacing between jobs

In Control, increase:

- `INTAKE_PACING_SECONDS`

That gives the shared GitHub-backed intake system more breathing room.

### 3. Avoid repeated manual `Run Now` bursts

If GitHub is already throttling, pressing `Run Now` repeatedly is not helpful. The better operator behavior is:

1. wait for the retry window
2. run once
3. watch alerts and incidents

### 4. Prefer one clean backlog sweep over repeated partial runs

Starting multiple overlapping operator runs is more likely to waste quota than letting one clean run complete.

### 5. Add better shared GitHub coordination later

The best future hardening is still a central GitHub cooldown gate shared by:

- Firehose
- Backfill
- Analyst
- any other GitHub-consuming worker

That would stop the whole GitHub-facing side of the system from rediscovering the same exhausted quota independently.

## Is This The Best Way For The Analyst To Work?

For the current architecture, mostly yes.

What is strong about the current design:

- taxonomy is controlled instead of chaotic
- missing README does not automatically mean agent failure
- evidence is extracted before interpretation
- strategic repos can get a deeper second pass
- GitHub rate limiting is now handled as temporary infrastructure pressure, not a repository-quality failure

What I think is still not ideal yet:

- heuristic mode still leans heavily on README content instead of using all evidence as deeply as it could
- GitHub rate limiting is handled safely after the fact, but prevention is still weaker than it should be
- shared GitHub quota awareness should be system-wide, not just agent-local

So my honest answer is:

- the current Analyst design is suitable and directionally strong
- the safety behavior is much better now
- the next best improvement is quota prevention and shared cooldown coordination, not another prompt tweak

## What Changed

### Analyst behavior

The Analyst now combines:

- README analysis
- deterministic repository evidence
- repository metadata
- evidence-backed scoring
- fast vs deep analysis modes

The result is stronger than the older shallow implementation and is no longer limited to simple README summarization.

### Control panel and agent-management changes

The control plane now exposes Analyst as a real configurable agent.

You can now see:

- provider mode
- model configuration
- API-key readiness
- shared GitHub pacing
- shared intake pacing
- a dedicated Analyst readiness state

You can also edit Analyst runtime settings from the Control panel.

### Repository detail changes

Repository detail now shows richer Analyst output, including:

- `analysis_mode`
- `analysis_outcome`
- confidence
- category confidence
- score breakdown
- contradictions
- missing information
- provider/model provenance
- long-form summary

## What Is Editable In Control

Open:

- `http://127.0.0.1:3000/control`

Select:

- `Analyst`

You should now see an `Agent Settings` card with a clearly visible editor entry point.

The Control panel should show one of these states:

### 1. `This section is editable`

Expected:

- a visible button such as `Open Analyst Editor`

When you click it, you should be able to change:

- `Provider mode`
- `Anthropic model`
- `Gemini-compatible base URL`
- `Gemini-compatible model`
- `GitHub request budget`
- `Inter-job pacing`

### 2. `Editor is open`

Expected:

- editable form fields
- `Save Settings`
- `Cancel`

### 3. `Loading editable settings`

Expected:

- temporary loading state while the Control panel fetches the editable config form

### 4. `Editable settings are not available yet`

This means the frontend is asking for editable Analyst settings but the backend process serving the API has not picked up the latest code yet.

If you see this, restart the backend stack and refresh the page.

## Exactly What You Can Change

The editable Analyst settings are:

- `ANALYST_PROVIDER`
  - `heuristic`
  - `llm`
  - `gemini`
- `ANALYST_MODEL_NAME`
- `GEMINI_BASE_URL`
- `GEMINI_MODEL_NAME`
- `GITHUB_REQUESTS_PER_MINUTE`
- `INTAKE_PACING_SECONDS`

What you cannot edit from the browser:

- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Those stay masked on purpose. The UI shows `configured` or `missing`, but it does not expose raw secrets.

## Analyst Readiness Card

The Control panel now includes an `Analyst Readiness` card.

It turns:

- green when the current Analyst mode is runnable
- yellow when the saved settings and the live worker view are out of sync
- red when the selected provider mode is missing a required API key

Examples:

- `Ready in heuristic mode`
- `Ready in Anthropic mode`
- `Ready in Gemini mode`
- `Pending worker sync`
- `Blocked by missing Anthropic key`
- `Blocked by missing Gemini key`

## Category And Tag Behavior

Yes. The Analyst is supposed to assign both a primary category and normalized tags.

### Primary category

The Analyst assigns:

- one primary `category`

This category is from a controlled vocabulary, not an open-ended free-text field.

Current controlled repository categories include:

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

### Agent tags

The Analyst also assigns:

- zero or more normalized `agent_tags`

These also come from a controlled vocabulary.

Examples of controlled tags include:

- `workflow`
- `automation`
- `api`
- `auth`
- `analytics`
- `commercial-ready`
- `hosted-gap`
- `saas-candidate`
- `self-hosted`
- `open-core-candidate`
- `react`
- `typescript`
- `python`
- `docker`
- `kubernetes`

### Unknown tags and categories

If the model proposes a category or tag outside the controlled vocabulary:

- it should not silently become canonical
- unknown categories should go to `suggested_new_categories`
- unknown tags should go to `suggested_new_tags`

That behavior is intentional. It keeps the catalog stable and prevents taxonomy drift.

## What To Expect In The Website

## Control Page

Open:

- `http://127.0.0.1:3000/control`

Select `Analyst`.

You should expect:

- queue-driven execution mode
- an `Analyst Readiness` card
- visible provider/model information
- editable settings entry point
- `Run Now` when the agent is not paused
- masked API-key readiness state

You should not expect:

- raw secret values
- direct editing of API keys in the browser

## Agents Page

Open:

- `http://127.0.0.1:3000/agents`

Select `Analyst`.

You should expect:

- live provider mode
- live model information
- Anthropic/Gemini configured state
- GitHub request budget
- shared intake pacing
- runtime notes and pause state

## Repositories Catalog

Open:

- `http://127.0.0.1:3000/repositories`

You should be able to:

- browse analyzed repositories
- filter by category
- inspect tags
- open detail pages for deeper analysis output

## Repository Detail Page

Open any analyzed repository.

You should expect to see:

- primary category
- category confidence
- normalized agent tags
- suggested new categories when the taxonomy is uncertain
- long-form Analyst summary
- score breakdown
- contradictions
- missing information
- provider/model provenance

## Manual Verification

## Legacy Repository Refresh

Repositories that were marked `completed` by the older Analyst but do not carry the new analysis schema are now treated as stale.

That means:

- they can be picked up again by the new Analyst
- you do not need to manually delete old rows first
- running Analyst again should refresh older accepted repositories into the new format

Fresh repositories that already have the current analysis schema are still skipped normally.

## Recommended Startup

From the project root:

```bash
./scripts/bootstrap.sh
./scripts/migrate.sh
./scripts/dev.sh
```

This should start:

- frontend on `http://127.0.0.1:3000`
- backend on `http://127.0.0.1:8000`
- workers

## Fastest UI-only test

1. Open `http://127.0.0.1:3000/control`
2. Select `Analyst`
3. Confirm the `Analyst Readiness` card appears
4. Confirm the `Agent Settings` card shows `Open Analyst Editor`
5. Click `Open Analyst Editor`
6. Change `Provider mode`
7. Click `Save Settings`
8. Confirm a save success message appears
9. Open `http://127.0.0.1:3000/agents`
10. Select `Analyst`
11. Confirm the live runtime view reflects the new mode
12. Open `http://127.0.0.1:3000/repositories`
13. Open an analyzed repository detail page
14. Confirm category, tags, confidence, and score output are visible

## End-to-end queue test

1. Open `http://127.0.0.1:3000/control`
2. Run `Firehose`
3. Run `Bouncer`
4. Run `Analyst`
5. Open `http://127.0.0.1:3000/repositories`
6. Find a repository that moved through analysis
7. Open its detail page
8. Confirm:
   - category exists or is explicitly unclear
   - agent tags appear normalized
   - suggested taxonomy fields appear when needed
   - analysis mode and outcome are visible

## Troubleshooting

## Problem: I only see static information in Control

If you do not see an `Open Analyst Editor` button and the Control panel looks static-only:

1. Look at the `Agent Settings` card
2. If it shows `Editable settings are not available yet`, restart the backend and refresh

Use:

```bash
cd /Users/bot/.openclaw/workspace/agentic-workflow
./scripts/dev.sh
```

If the stack is already running on ports `3000` and `8000`, stop the existing copy first or refresh the already running site after the backend reloads.

## Problem: Analyst is set to `llm` but shows blocked

Cause:

- `ANTHROPIC_API_KEY` is missing in the live worker/backend environment

Fix:

- add the key to `backend/.env` and `workers/.env`
- restart the worker loop

## Problem: Analyst is set to `gemini` but shows blocked

Cause:

- `GEMINI_API_KEY` is missing in the live worker/backend environment

Fix:

- add the key to `backend/.env` and `workers/.env`
- restart the worker loop

## Problem: I changed settings but the live runtime still looks old

Cause:

- the saved settings and live worker process are out of sync

Signal:

- readiness card shows `Pending worker sync`

Fix:

- restart the worker loop so automatic runs use the new settings

## Required Configuration

### Minimum GitHub configuration

```bash
GITHUB_PROVIDER_TOKEN=your_github_token
```

### Heuristic mode

```bash
ANALYST_PROVIDER=heuristic
```

### Anthropic-backed mode

```bash
ANALYST_PROVIDER=llm
ANTHROPIC_API_KEY=your_key
ANALYST_MODEL_NAME=claude-3-5-haiku-20241022
```

### Gemini-compatible mode

```bash
ANALYST_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_BASE_URL=https://api.haimaker.ai/v1
GEMINI_MODEL_NAME=google/gemini-2.0-flash-001
```

## Files You Should Care About

### Worker-side Analyst logic

- [readme_analyst.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/providers/readme_analyst.py)
- [repository_evidence.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/providers/repository_evidence.py)
- [analyst_job.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/jobs/analyst_job.py)
- [analysis_store.py](/Users/bot/.openclaw/workspace/agentic-workflow/workers/agentic_workers/storage/analysis_store.py)

### Control-plane and configuration

- [page.tsx](/Users/bot/.openclaw/workspace/agentic-workflow/frontend/src/app/control/page.tsx)
- [AgentsClient.tsx](/Users/bot/.openclaw/workspace/agentic-workflow/frontend/src/app/agents/AgentsClient.tsx)
- [agents.ts](/Users/bot/.openclaw/workspace/agentic-workflow/frontend/src/api/agents.ts)
- [agent_config_service.py](/Users/bot/.openclaw/workspace/agentic-workflow/backend/app/services/agent_config_service.py)
- [project_validator.py](/Users/bot/.openclaw/workspace/agentic-workflow/backend/app/services/settings/project_validator.py)
- [worker_projector.py](/Users/bot/.openclaw/workspace/agentic-workflow/backend/app/services/settings/worker_projector.py)

### Repository detail output

- [RepositoryDetailClient.tsx](/Users/bot/.openclaw/workspace/agentic-workflow/frontend/src/components/repositories/RepositoryDetailClient.tsx)
- [repositories.ts](/Users/bot/.openclaw/workspace/agentic-workflow/frontend/src/api/repositories.ts)
- [repository_exploration_service.py](/Users/bot/.openclaw/workspace/agentic-workflow/backend/app/services/repository_exploration_service.py)

## Verification Already Run

The latest verification after these changes:

- backend tests passed
- frontend production build passed
- backend lint passed on touched files

## Future Work

Still future work from the larger roadmap:

- dedicated `analysis_evidence` artifact kind
- dedicated optional `analysis_selected_files` artifact kind
- separate maintainer-intelligence phase
- broader catalog indicators and score-driven filtering
- deeper taxonomy governance beyond the current controlled lists
