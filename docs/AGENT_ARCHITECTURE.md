# Agentic Workflow - Complete Agent Architecture Documentation

## Overview

The Agentic Workflow is a local-first orchestration system for intelligent repository discovery, analysis, and idea synthesis. It consists of multiple specialized agents that work together in a pipeline to discover GitHub repositories, filter them, analyze their READMEs, and synthesize business opportunities.

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENTIC WORKFLOW SYSTEM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │  FRONTEND   │───▶│   BACKEND   │───▶│   WORKERS   │───▶│   SQLITE    │  │
│  │  (Next.js)  │◀───│  (FastAPI)  │◀───│  (Python)   │◀───│    (DB)     │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│        │                  │                  │                             │
│   Port 3000           Port 8000         Background                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Agents Overview

The system has 7 defined agents. Here's the complete breakdown:

| Agent | Status | Uses LLM | Uses GitHub API | Purpose |
|-------|--------|----------|-----------------|---------|
| **Overlord** | Placeholder | No | No | Control-plane coordinator (dashboard-visible only) |
| **Firehose** | Live | No | Yes | Discovers repositories from GitHub new/trending feeds |
| **Backfill** | Live | No | Yes | Replays older GitHub repository windows for historical coverage |
| **Bouncer** | Live | No | No | Applies local include/exclude rules to filter repositories |
| **Analyst** | Live | **Yes** (configurable) | Yes | Builds evidence-backed repository analysis with fast/deep modes |
| **Combiner** | Live | **Yes** (optional) | No | Synthesizes multi-repository opportunities |
| **Obsession** | Partial | No | No | Tracks obsession contexts, memory, and refresh triggers |

---

## Detailed Agent Descriptions

### 1. Overlord Agent

**Status:** Placeholder (Dashboard-visible only)

**Purpose:** Control-plane coordinator

**Implementation:** No standalone worker loop currently runs. It exists as a concept in the dashboard roster but has no active execution.

**Uses LLM:** No  
**Uses GitHub API:** No  
**Configured Provider:** None

**Notes:**
- Shown in the UI roster for completeness
- No model or token usage tracking
- Reserved for future control-plane coordination functionality

---

### 2. Firehose Agent

**Status:** Live (Active worker)

**Purpose:** Repository intake from GitHub's live feeds

**Implementation:** `workers/agentic_workers/jobs/firehose_job.py`

**Uses LLM:** No  
**Uses GitHub API:** Yes (requires `GITHUB_PROVIDER_TOKEN`)  
**Configured Provider:** GitHub

**Function Details:**

The Firehose agent continuously polls GitHub's search API to discover new and trending repositories. It operates in two modes:

1. **NEW Mode:** Discovers recently created repositories
2. **TRENDING Mode:** Discovers repositories gaining traction

**Key Behaviors:**
- Runs on a configurable interval (default: 3600 seconds / 1 hour)
- Respects GitHub rate limits with automatic backoff
- Maintains checkpoint state to resume after interruptions
- Persists discovered repositories to the intake queue
- Handles pagination and date anchoring for consistent discovery

**Configuration:**
```python
FIREHOSE_INTERVAL_SECONDS = 3600  # How often to run
FIREHOSE_PER_PAGE = 100           # Results per page
FIREHOSE_PAGES = 3                # Pages to fetch per run
```

**Output:**
- Repository records in `RepositoryIntake` table
- Run artifacts in `runtime/firehose/ingestion-runs/`

---

### 3. Backfill Agent

**Status:** Live (Active worker)

**Purpose:** Historical repository discovery to fill coverage gaps

**Implementation:** `workers/agentic_workers/jobs/backfill_job.py`

**Uses LLM:** No  
**Uses GitHub API:** Yes (requires `GITHUB_PROVIDER_TOKEN`)  
**Configured Provider:** GitHub

**Function Details:**

The Backfill agent discovers older repositories by working backwards through time windows. It's essential for building historical coverage beyond what Firehose captures.

**Key Behaviors:**
- Works backwards from recent dates to older dates
- Uses sliding time windows (default: 30 days)
- Handles pagination with cursor-based navigation for dense result sets
- Detects window exhaustion and advances to older periods
- Shares rate limit budget with Firehose

**Configuration:**
```python
BACKFILL_INTERVAL_SECONDS = 21600  # 6 hours between runs
BACKFILL_PER_PAGE = 100            # Results per page
BACKFILL_PAGES = 2                 # Pages per run
BACKFILL_WINDOW_DAYS = 30          # Size of each time window
BACKFILL_MIN_CREATED_DATE = date(2008, 1, 1)  # How far back to go
```

**Output:**
- Repository records in `RepositoryIntake` table
- Run artifacts in `runtime/backfill/ingestion-runs/`

---

### 4. Bouncer Agent

**Status:** Live (Active worker)

**Purpose:** Rule-based triage/filtering of repository intake

**Implementation:** `workers/agentic_workers/jobs/bouncer_job.py`

**Uses LLM:** No  
**Uses GitHub API:** No  
**Configured Provider:** Local rules engine

**Function Details:**

The Bouncer is a deterministic rules engine that filters repositories based on include/exclude patterns. It processes repositories in the PENDING triage state and decides whether to ACCEPT or REJECT them.

**Rule Matching:**
- Uses word-boundary regex matching (e.g., "saas" won't match "isaas")
- Case-insensitive matching
- Checks both repository name and description

**Rule Priority:**
1. **Exclude rules** take priority - if any match, repository is REJECTED
2. **Include rules** - if configured and none match, repository is REJECTED
3. **Pass-through** - if no include rules configured and no exclude rules match, repository is ACCEPTED

**Configuration:**
```python
BOUNCER_INCLUDE_RULES = ("saas", "api", "platform")  # Accept only these
BOUNCER_EXCLUDE_RULES = ("personal", "deprecated")   # Always reject these
```

**Decision Types:**

| Triage Status | Explanation Kind | When Applied |
|---------------|------------------|--------------|
| ACCEPTED | INCLUDE_RULE | Matched include rules |
| ACCEPTED | PASS_THROUGH | No rules configured, no exclude match |
| REJECTED | EXCLUDE_RULE | Matched exclude rules |
| REJECTED | ALLOWLIST_MISS | Include rules configured but none matched |

**Output:**
- Updated `RepositoryIntake` records with triage_status
- Triage explanations in `RepositoryTriageExplanation` table
- Run artifacts in `runtime/bouncer/triage-runs/`

---

### 5. Analyst Agent

**Status:** Live (Active worker)

**Purpose:** README fetching and business analysis

**Implementation:** `workers/agentic_workers/jobs/analyst_job.py`

**Uses LLM:** Yes (configurable fast/deep analysis)  
**Uses GitHub API:** Yes (requires `GITHUB_PROVIDER_TOKEN`)  
**Configured Provider:** Configurable analyst provider (`heuristic`, Anthropic LLM, or Gemini-compatible)

**Function Details:**

The Analyst fetches README content plus lightweight repository intelligence from GitHub and produces an evidence-backed business analysis for accepted repositories. It supports a fast pass for broad coverage and a deeper pass for stronger candidates.

**Process:**
1. Finds repositories with `triage_status=ACCEPTED` and incomplete analysis
2. Fetches README from GitHub API
3. Fetches deterministic repo evidence (metadata, contributors, releases, commits, PRs, issues, tree signals, selected manifest files)
4. Normalizes README (removes badges, license sections, etc.)
5. Builds structured evidence, contradictions, score breakdowns, and semantic outcomes
6. Runs fast analysis, then optionally deep analysis for high-potential repos
7. Persists analysis results and artifacts

**README Normalization:**
- Removes badge lines
- Strips license/contributing sections
- Removes markdown links and images
- Collapses excessive whitespace
- Truncates to 8000 characters

**Analysis Dimensions:**

| Dimension | Description |
|-----------|-------------|
| monetization_potential | LOW / MEDIUM / HIGH |
| category / agent_tags | Controlled taxonomy plus suggested expansions |
| confidence | Category confidence, overall confidence, semantic outcome |
| score_breakdown | Technical maturity, commercial readiness, hosted gap, market timing, trust risk |
| pros | Positive business signals detected |
| cons | Risk signals or missing information |
| missing_feature_signals | Specific features not mentioned |
| contradictions | Tension between README claims and observed repo evidence |

**Artifacts:**

- `RepositoryAnalysisResult` records
- README artifacts in `runtime/data/readmes/`
- Analysis artifacts in `runtime/analyst/analysis-runs/`
- Persisted source metadata with provider/model/token usage, evidence summaries, contradictions, and score breakdowns

---

### 6. Combiner Agent

**Status:** Live (Active worker)

**Purpose:** Multi-repository synthesis and opportunity generation

**Implementation:** `workers/agentic_workers/jobs/combiner_job.py`

**Uses LLM:** Yes (optional - Anthropic Claude)  
**Uses GitHub API:** No  
**Configured Provider:** Anthropic (if API key available) or Heuristic fallback

**Function Details:**

The Combiner is the only agent that uses LLM capabilities. It synthesizes insights from multiple repositories to propose composite business opportunities.

**Two Implementations:**

#### A. AnthropicCombinerProvider (LLM-based)
**Model:** Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`)

**Prompt Structure:**
```
Given these N repository READMEs, propose a composite business opportunity that combines their strengths.

[Previous Insights - if available]

## Repository 1: owner/repo
[README content]

## Repository 2: owner/repo
[README content]
...

Provide a concise synthesis (200-400 words) covering:
1. What composite opportunity emerges from combining these projects
2. Key value proposition for potential customers
3. Market positioning and differentiation
4. Next steps for validation
```

**Memory Integration:**
- Loads previous insights from `AgentMemorySegment` when an obsession context exists
- Builds upon prior synthesis work iteratively
- Persists new insights back to memory after completion

#### B. HeuristicCombinerProvider (Fallback)
When no Anthropic API key is configured, uses pattern matching:
- Extracts themes (API, automation, analytics, collaboration)
- Generates structured output with standard sections
- No LLM tokens consumed

**Output:**
- `SynthesisRun` records with status COMPLETED
- Structured output: title, summary, key_insights
- Memory segments written if obsession context exists

**Configuration:**
```bash
# Required for LLM mode
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

### 7. Obsession Agent

**Status:** Partial (Workflow state tracking)

**Purpose:** Long-lived context tracking for synthesis work

**Implementation:** `backend/app/services/obsession_service.py`

**Uses LLM:** No (indirect - triggers synthesis jobs that may use LLM)  
**Uses GitHub API:** No  
**Configured Provider:** Workflow state

**Function Details:**

The Obsession agent manages "obsession contexts" - persistent workspaces for tracking multi-run synthesis work on specific idea families or concepts.

**Core Concepts:**

1. **Obsession Context:** A container for related synthesis work
   - Can be attached to an IdeaFamily OR a SynthesisRun
   - Has refresh policies: manual, daily, weekly
   - Maintains memory segments across runs

2. **Memory Segments:** Key-value storage for context
   - `insights`: Previous synthesis insights (JSON array)
   - `title`: Generated title
   - `summary`: Generated summary

**API Endpoints:**
- `POST /api/v1/obsession/contexts` - Create context
- `GET /api/v1/obsession/contexts` - List contexts
- `GET /api/v1/obsession/contexts/{id}` - Get detail with history
- `POST /api/v1/obsession/contexts/{id}/refresh` - Trigger refresh

**Refresh Flow:**
1. User or schedule triggers refresh
2. Creates new `SynthesisRun` with `run_type="obsession"`
3. Associates run with obsession context
4. Combiner processes run with memory context loaded
5. Results persisted back to memory segments

---

## Data Flow Pipeline

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         REPOSITORY PROCESSING PIPELINE                      │
└────────────────────────────────────────────────────────────────────────────┘

     ┌──────────┐
     │ GitHub   │
     │ API      │
     └────┬─────┘
          │
          ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   FIREHOSE      │────▶│   BACKFILL      │────▶│   INTAKE QUEUE  │
│   (Live Feed)   │     │   (Historical)  │     │   (Pending)     │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │    BOUNCER      │
                                               │  (Rule Filter)  │
                                               └────────┬────────┘
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    │                   │                   │
                                    ▼                   ▼                   ▼
                           ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                           │  REJECTED   │     │   ACCEPTED  │     │   FAILED    │
                           │  (Excluded) │     │  (To Analyz)│     │  (Error)    │
                           └─────────────┘     └──────┬──────┘     └─────────────┘
                                                      │
                                                      ▼
                                            ┌─────────────────┐
                                            │     ANALYST     │
                                            │ (README Analyze)│
                                            └────────┬────────┘
                                                     │
                                    ┌────────────────┼────────────────┐
                                    │                │                │
                                    ▼                ▼                ▼
                           ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
                           │  ANALYZED   │  │   FAILED    │  │   SKIPPED   │
                           │ (Ready for  │  │ (No README/ │  │  (No work)  │
                           │  synthesis) │  │   Error)    │  │             │
                           └──────┬──────┘  └─────────────┘  └─────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    COMBINER     │
                         │  (Synthesis -   │
                         │   Optional LLM) │
                         └────────┬────────┘
                                  │
                     ┌────────────┼────────────┐
                     │            │            │
                     ▼            ▼            ▼
            ┌─────────────┐ ┌────────────┐ ┌────────────┐
            │  COMPLETED  │ │   FAILED   │ │  PENDING   │
            │ (Insights + │ │  (Error)   │ │ (Queued)   │
            │   Memory)   │ │            │ │            │
            └─────────────┘ └────────────┘ └────────────┘
```

---

## Tag System

### Who Adds Tags?

**Tags are NOT automatically added by agents.** The current system does not have automatic tag generation.

**Tag Sources:**

1. **User-Curated Tags** (`RepositoryUserTag` model)
   - Users manually tag repositories via the UI
   - Stored in `repository_user_tag` table
   - Linked to repositories by `github_repository_id`

2. **Idea Family Membership** (`IdeaFamilyMembership` model)
   - Repositories can be added to "Idea Families"
   - This is a grouping mechanism rather than free-form tags
   - Stored in `idea_family_membership` table

3. **Future: LLM-Generated Tags** (not implemented)
   - Could be added by the Analyst agent
   - Would extract themes/topics from README analysis
   - Not currently active in the codebase

### Tag-Related Database Tables

```sql
-- User-defined tags
repository_user_tag (
    id INTEGER PRIMARY KEY,
    github_repository_id INTEGER NOT NULL,
    tag VARCHAR NOT NULL,
    created_at TIMESTAMP
)

-- Idea families (conceptual groupings)
idea_family (
    id INTEGER PRIMARY KEY,
    title VARCHAR NOT NULL,
    description TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

idea_family_membership (
    id INTEGER PRIMARY KEY,
    idea_family_id INTEGER NOT NULL,
    github_repository_id INTEGER NOT NULL,
    added_at TIMESTAMP
)
```

---

## Memory System

### AgentMemorySegment

Memory segments provide persistent storage for synthesis agents across multiple runs.

**Structure:**
```python
AgentMemorySegment(
    id: int                    # Primary key
    obsession_context_id: int  # Links to obsession context
    segment_key: str          # e.g., "insights", "title", "summary"
    content: str              # The actual content
    content_type: str         # e.g., "json", "markdown"
    created_at: datetime
    updated_at: datetime
)
```

**Usage Flow:**
1. User creates obsession context
2. Combiner loads previous insights (if any) via `MemoryRepository`
3. Combiner runs synthesis with context
4. Combiner writes new insights back to memory
5. Next run loads accumulated insights

---

## Configuration Reference

### Environment Variables

| Variable | Required By | Purpose |
|----------|-------------|---------|
| `GITHUB_PROVIDER_TOKEN` | Firehose, Backfill, Analyst | GitHub API authentication |
| `ANTHROPIC_API_KEY` | Combiner (LLM mode) | Anthropic Claude API access |
| `DATABASE_URL` | All | SQLite database path |
| `AGENTIC_RUNTIME_DIR` | All | Runtime artifacts directory |

### Worker Configuration (workers/agentic_workers/core/config.py)

```python
# Pacing and rate limits
GITHUB_REQUESTS_PER_MINUTE = 60      # Shared across GitHub-using agents
INTAKE_PACING_SECONDS = 30           # Delay between API calls

# Firehose tuning
FIREHOSE_INTERVAL_SECONDS = 3600     # 1 hour
FIREHOSE_PER_PAGE = 100
FIREHOSE_PAGES = 3

# Backfill tuning
BACKFILL_INTERVAL_SECONDS = 21600    # 6 hours
BACKFILL_PER_PAGE = 100
BACKFILL_PAGES = 2
BACKFILL_WINDOW_DAYS = 30

# Bouncer rules (set via env as comma-separated)
BOUNCER_INCLUDE_RULES = ()
BOUNCER_EXCLUDE_RULES = ()
```

---

## Agent Run Tracking

Every agent run is tracked in the `AgentRun` table:

```python
AgentRun(
    id: int
    agent_name: str           # e.g., "firehose", "analyst"
    status: AgentRunStatus    # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, SKIPPED_PAUSED
    started_at: datetime
    completed_at: datetime
    items_processed: int
    items_succeeded: int
    items_failed: int
    provider_name: str        # e.g., "github", "anthropic"
    model_name: str          # e.g., "claude-3-5-sonnet-20241022"
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_summary: str
    error_context: str
)
```

---

## Failure Handling & Pause System

Agents can be automatically paused when failures occur:

**Failure Classification:**
- `RATE_LIMITED` - API rate limit hit
- `AUTHENTICATION_ERROR` - Invalid credentials
- `TRANSIENT_ERROR` - Temporary network/API issue
- `BLOCKING` - Non-recoverable error

**Pause Policy:**
- Evaluated after each failure
- Can pause individual agents or agent groups
- Resume conditions tracked in `AgentPauseState`

**Pause State:**
```python
AgentPauseState(
    id: int
    agent_name: str
    is_paused: bool
    paused_at: datetime
    paused_by_event_id: int
    reason: str
    resume_condition: str
)
```

---

## File Locations

### Agent Implementations

| Agent | Implementation File |
|-------|---------------------|
| Firehose | `workers/agentic_workers/jobs/firehose_job.py` |
| Backfill | `workers/agentic_workers/jobs/backfill_job.py` |
| Bouncer | `workers/agentic_workers/jobs/bouncer_job.py` |
| Analyst | `workers/agentic_workers/jobs/analyst_job.py` |
| Combiner | `workers/agentic_workers/jobs/combiner_job.py` |
| Obsession | `backend/app/services/obsession_service.py` |

### Provider Implementations

| Provider | File |
|----------|------|
| GitHubProvider | `workers/agentic_workers/providers/github_provider.py` |
| HeuristicReadmeAnalysisProvider | `workers/agentic_workers/providers/readme_analyst.py` |
| AnthropicCombinerProvider | `workers/agentic_workers/providers/combiner_provider.py` |
| HeuristicCombinerProvider | `workers/agentic_workers/providers/combiner_provider.py` |

### Service Layer

| Service | File |
|---------|------|
| ObsessionService | `backend/app/services/obsession_service.py` |
| MemoryService | `backend/app/services/memory_service.py` |
| AgentMetadata | `backend/app/services/agent_metadata.py` |

---

## Key Design Decisions

1. **Heuristic over LLM for most agents:** Only Combiner uses LLM; others use deterministic logic for cost control and predictability.

2. **Shared GitHub token budget:** Firehose and Backfill share rate limits via calculated pacing.

3. **Checkpoint-based resumption:** All intake agents can resume interrupted runs without duplication.

4. **Artifact-based debugging:** Every run produces JSON artifacts for inspection.

5. **Separation of concerns:** Backend handles API/state; Workers handle background processing.

6. **Memory for synthesis continuity:** Obsession contexts enable iterative, long-lived synthesis work.

---

*Generated from codebase analysis - reflects current implementation as of March 2026*
