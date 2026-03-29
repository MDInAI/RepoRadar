# Implementation Plan: Deep Synthesis Pipeline

## Goal
Allow the user to select any scout search results (or subset), feed them into the combiner for deep comparative analysis, and set up obsession to watch for new repos — all generic, not tied to any specific topic.

---

## Phase 1: Bulk-add scout results to an idea family

**Why**: The bridge between Scout and Ideas pages. Currently you can only add repos to a family one at a time. You need to select scout results and push them into a family in one action.

### Backend changes

**1a. New endpoint: `POST /api/v1/idea-families/{family_id}/members/bulk`**

File: `backend/app/api/routes/idea_families.py`

```python
class BulkMembershipRequest(BaseModel):
    github_repository_ids: list[int] = Field(min_length=1, max_length=500)

@router.post("/{family_id}/members/bulk")
def bulk_add_repositories(family_id: int, request: BulkMembershipRequest, ...):
    added_count = service.bulk_add_repositories(family_id, request.github_repository_ids)
    return {"added_count": added_count}
```

File: `backend/app/schemas/idea_family.py` — add `BulkMembershipRequest` schema.

File: `backend/app/services/idea_family_service.py` — add `bulk_add_repositories()` method that:
- Validates family exists
- Filters out already-existing members (skip duplicates)
- Bulk-inserts new `IdeaFamilyMembership` rows
- Returns count of newly added repos

**1b. New endpoint: `POST /api/v1/idea-families/from-search`**

Convenience shortcut: create a family AND populate it from a scout search in one call.

File: `backend/app/api/routes/idea_families.py`

```python
class CreateFamilyFromSearchRequest(BaseModel):
    idea_search_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    only_analyzed: bool = False  # If true, only include repos with analysis_status=COMPLETED

@router.post("/from-search")
def create_family_from_search(request: CreateFamilyFromSearchRequest, ...):
    # 1. Create new IdeaFamily
    # 2. Query all IdeaSearchDiscovery for search_id → get github_repository_ids
    # 3. Optionally filter to only analyzed repos
    # 4. Bulk-insert memberships
    # Returns: { family_id, title, member_count }
```

### Frontend changes

**1c. "Create Family from Results" button on Scout detail page**

File: `frontend/src/components/scout/IdeaSearchDetailView.tsx`

- Add a button: "Create Idea Family from Results" (shown when search has discoveries)
- Opens a dialog asking for: family title, description, checkbox "only analyzed repos"
- Calls `POST /idea-families/from-search`
- On success: shows link to the Ideas page with the new family selected

**1d. API client function**

File: `frontend/src/api/idea-families.ts` (or wherever the idea family API lives)
- Add `createFamilyFromSearch(searchId, title, description, onlyAnalyzed)` function

---

## Phase 2: Upgrade combiner for deep synthesis

**Why**: Current combiner takes 2-3 repos and produces a short summary. You need it to handle 20-50+ repos with deep comparative analysis using a thinking model.

### Backend changes

**2a. Add new synthesis run type: `"deep_synthesis"`**

File: `backend/app/models/repository.py` — add to `SynthesisRunType` enum:
```python
class SynthesisRunType(str, Enum):
    COMBINER = "combiner"
    OBSESSION = "obsession"
    DEEP_SYNTHESIS = "deep_synthesis"  # NEW
```

**2b. New endpoint or update existing: trigger deep synthesis on a family**

File: `backend/app/api/routes/synthesis.py` (or idea_families.py)

- Either extend the existing synthesis trigger to accept `run_type="deep_synthesis"`
- Or add a dedicated endpoint: `POST /api/v1/idea-families/{family_id}/deep-synthesis`
- Creates a `SynthesisRun` with:
  - `run_type = "deep_synthesis"`
  - `input_repository_ids` = ALL member repo IDs from the family
  - `status = "pending"`
- Remove the 2-3 repo limit validation for deep_synthesis type

### Worker changes

**2c. New provider: `DeepSynthesisProvider`**

File: `workers/agentic_workers/providers/deep_synthesis_provider.py` (NEW)

Uses Claude Opus with extended thinking. The prompt structure:

```python
SYSTEM_PROMPT = """You are a senior research analyst and systems architect. You are given
README files and analysis summaries from multiple open-source repositories, all related
to a common theme chosen by the user.

Your job is to produce a comprehensive strategic synthesis that:
1. Catalogs each repository's approach, architecture, and key innovations
2. Compares and ranks approaches (what works best, what doesn't)
3. Identifies the best components and ideas from across all repos
4. Proposes an ideal architecture that combines the best of everything
5. Identifies gaps — what's missing from existing solutions
6. Suggests a concrete roadmap with phases
7. Notes future opportunities and research directions

Be thorough, specific, and opinionated. Cite specific repositories when making claims.
Output in markdown."""

USER_PROMPT_TEMPLATE = """## Research Context

The user's research focus: {idea_text}

## Repositories Under Analysis ({repo_count} total)

{repo_sections}

{previous_insights_section}

---

Produce your deep synthesis now. Be comprehensive — this is a strategic research document,
not a summary. The user wants to build the best possible solution by learning from all
of these projects."""
```

Each repo section includes:
- Full name + stars + description
- README content (truncated to ~4000 chars per repo if needed to fit context)
- Analysis result artifact if available

Provider implementation:
```python
class DeepSynthesisProvider:
    def __init__(self, api_key: str, model: str = "claude-opus-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def synthesize(self, repo_contents: list[dict], idea_text: str,
                   previous_insights: str | None = None) -> CombinerSynthesisResult:
        # Build prompt from template
        # Call with extended thinking enabled (budget_tokens=10000)
        # Parse response
        # Return CombinerSynthesisResult with output_text, title, summary, key_insights
```

**2d. Update combiner_job.py to handle deep_synthesis runs**

File: `workers/agentic_workers/jobs/combiner_job.py`

- In the job's pending query: also match `run_type == "deep_synthesis"` (not just "combiner")
- When `run_type == "deep_synthesis"`:
  - Load the idea family to get `idea_text` context (from the family's linked search or description)
  - Load BOTH `README_SNAPSHOT` and `ANALYSIS_RESULT` artifacts per repo
  - Use `DeepSynthesisProvider` instead of `AnthropicCombinerProvider`
  - No repo count limit
- Keep existing combiner flow unchanged for `run_type == "combiner"`

**2e. Parse deep synthesis output**

The deep synthesis output is a full markdown document. Add a parser that extracts:
- `title`: First H1 heading
- `summary`: First paragraph or executive summary section
- `key_insights`: Bullet points from a "Key Findings" or "Recommendations" section
- `output_text`: The full document

File: `workers/agentic_workers/jobs/combiner_job.py` — add `parse_deep_synthesis_output()` function.

### Frontend changes

**2f. "Deep Synthesis" button on Ideas page**

File: `frontend/src/app/ideas/page.tsx` and `SynthesisControlDock` component

- Add a "Deep Synthesis" button (distinct from the existing combiner synthesis)
- Triggers `POST /idea-families/{family_id}/deep-synthesis`
- Shows progress/status in `SynthesisHistoryPanel`
- When complete, the `SynthesisRunDetailDialog` renders the full markdown output

---

## Phase 3: Connect obsession to scout searches

**Why**: The obsession system already supports forward-watching idea searches. You just need it wired up from the UI flow so you can set it up from the scout or ideas page.

### Backend changes

**3a. Update obsession context creation to accept `idea_search_id` directly**

File: `backend/app/services/obsession_service.py`

Currently obsession requires ONE of: `idea_family_id`, `synthesis_run_id`, or `idea_text`.
Add a fourth option: `idea_search_id` — link to an existing scout search instead of creating a new one.

File: `backend/app/schemas/obsession.py`:
```python
class ObsessionContextCreateRequest(BaseModel):
    idea_family_id: int | None = None
    synthesis_run_id: int | None = None
    idea_search_id: int | None = None  # NEW: link to existing scout search
    idea_text: str | None = None
    title: str
    description: str | None = None
    refresh_policy: str = "manual"
```

Validation: exactly ONE of the four fields must be provided.

If `idea_search_id` is provided:
- Validate the search exists
- Create obsession context linked to that search
- The search's direction should be flipped to "forward" if it's "backward" (or create a new forward search with same queries)

### Frontend changes

**3b. "Watch for New Repos" button on Scout detail page**

File: `frontend/src/components/scout/IdeaSearchDetailView.tsx`

- Add button: "Create Obsession Watch"
- Opens dialog: title, description, refresh policy (manual/daily/weekly)
- Calls obsession create with `idea_search_id`
- Shows confirmation with link to Ideas page

**3c. "Create Obsession" option on Ideas page family view**

This already exists in the `ObsessionContextPanel` component. Verify it works end-to-end:
- Create obsession with `idea_family_id`
- Optionally provide `idea_text` for forward watching
- Refresh triggers combiner synthesis

---

## Phase 4: End-to-end flow verification

The complete user workflow should be:

1. **Scout page**: Create search → queries run → repos discovered → analyst analyzes them
2. **Scout page**: Click "Create Idea Family from Results" → family created with all repos
3. **Ideas page**: Select family → Click "Deep Synthesis" → Opus produces comprehensive strategy doc
4. **Ideas page**: Create obsession context linked to family or search → auto-watches for new repos
5. **Ideas page**: When obsession detects new repos → triggers new synthesis incorporating new findings

---

## File change summary

### New files
- `workers/agentic_workers/providers/deep_synthesis_provider.py`

### Modified backend files
- `backend/app/api/routes/idea_families.py` — bulk-add + from-search endpoints
- `backend/app/schemas/idea_family.py` — BulkMembershipRequest, CreateFamilyFromSearchRequest
- `backend/app/services/idea_family_service.py` — bulk_add_repositories, create_from_search
- `backend/app/api/routes/synthesis.py` — deep synthesis trigger endpoint
- `backend/app/models/repository.py` — DEEP_SYNTHESIS enum value
- `backend/app/schemas/obsession.py` — add idea_search_id field
- `backend/app/services/obsession_service.py` — handle idea_search_id

### Modified worker files
- `workers/agentic_workers/jobs/combiner_job.py` — handle deep_synthesis run type
- `workers/agentic_workers/main.py` — config for deep synthesis provider (model, API key)

### Modified frontend files
- `frontend/src/components/scout/IdeaSearchDetailView.tsx` — "Create Family" + "Watch" buttons
- `frontend/src/app/ideas/page.tsx` — "Deep Synthesis" button
- `frontend/src/api/idea-families.ts` — new API functions
- `frontend/src/api/synthesis.ts` — deep synthesis trigger

### Database migration
- Add `"deep_synthesis"` to synthesis_run.run_type CHECK constraint
