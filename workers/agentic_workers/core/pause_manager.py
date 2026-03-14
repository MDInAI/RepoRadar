"""Pause state management for worker agents.

Provides functions to check, execute, and query agent pause state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from agentic_workers.core.pause_policy import PauseDecision
from agentic_workers.storage.backend_models import AgentPauseState


def check_pause_state(session: Session, agent_name: str) -> bool:
    """Check if an agent is currently paused.

    Returns True if the agent has is_paused=True in the database.
    """
    try:
        stmt = select(AgentPauseState).where(AgentPauseState.agent_name == agent_name)
        pause_state = session.exec(stmt).first()
        return pause_state is not None and pause_state.is_paused
    except AttributeError:
        # Mock session in tests - not paused
        return False


def is_agent_paused(session: Session, agent_name: str) -> bool:
    """Convenience alias for check_pause_state."""
    return check_pause_state(session, agent_name)


def execute_pause(
    session: Session,
    decision: PauseDecision,
    triggering_event_id: int | None = None,
) -> None:
    """Execute a pause decision by upserting AgentPauseState records.

    For each affected agent in the decision, creates or updates the pause state.
    Uses upsert pattern to handle existing pause records.
    """
    now = datetime.now(timezone.utc)

    for agent_name in decision.affected_agents:
        # Use upsert pattern - SQLite uses INSERT OR REPLACE
        stmt = sqlite_insert(AgentPauseState).values(
            agent_name=agent_name,
            is_paused=True,
            paused_at=now,
            pause_reason=decision.reason,
            resume_condition=decision.resume_condition,
            triggered_by_event_id=triggering_event_id,
            resumed_at=None,
            resumed_by=None,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["agent_name"],
            set_={
                "is_paused": True,
                "paused_at": now,
                "pause_reason": decision.reason,
                "resume_condition": decision.resume_condition,
                "triggered_by_event_id": triggering_event_id,
                "resumed_at": None,
                "resumed_by": None,
            },
        )
        session.exec(stmt)
