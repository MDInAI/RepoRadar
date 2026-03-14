from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    # Workers currently reuse the sibling backend package as the authoritative
    # home of shared SQLModel queue contracts.
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import (  # noqa: E402
    AGENT_NAMES,
    AgentMemorySegment,
    AgentPauseState,
    AgentRun,
    AgentRunStatus,
    BackfillProgress,
    EventSeverity,
    FailureClassification,
    FailureSeverity,
    FirehoseProgress,
    RepositoryArtifact,
    RepositoryArtifactKind,
    RepositoryAnalysisFailureCode,
    RepositoryAnalysisResult,
    RepositoryAnalysisStatus,
    RepositoryCategory,
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryMonetizationPotential,
    RepositoryQueueStatus,
    RepositoryTriageExplanation,
    RepositoryTriageExplanationKind,
    RepositoryTriageStatus,
    SQLModel,
    SynthesisRun,
    SynthesisRunStatus,
    SystemEvent,
    exhausted_backfill_boundary,
)

__all__ = [
    "AGENT_NAMES",
    "AgentMemorySegment",
    "AgentPauseState",
    "AgentRun",
    "AgentRunStatus",
    "BackfillProgress",
    "EventSeverity",
    "FailureClassification",
    "FailureSeverity",
    "FirehoseProgress",
    "RepositoryArtifact",
    "RepositoryArtifactKind",
    "RepositoryAnalysisFailureCode",
    "RepositoryAnalysisResult",
    "RepositoryAnalysisStatus",
    "RepositoryCategory",
    "RepositoryDiscoverySource",
    "RepositoryFirehoseMode",
    "RepositoryIntake",
    "RepositoryMonetizationPotential",
    "RepositoryQueueStatus",
    "RepositoryTriageExplanation",
    "RepositoryTriageExplanationKind",
    "RepositoryTriageStatus",
    "SQLModel",
    "SynthesisRun",
    "SynthesisRunStatus",
    "SystemEvent",
    "exhausted_backfill_boundary",
]
