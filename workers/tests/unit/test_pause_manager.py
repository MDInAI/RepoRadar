"""Unit tests for pause manager."""
import pytest
from sqlmodel import Session, create_engine, select

from agentic_workers.core.pause_manager import check_pause_state, execute_pause, is_agent_paused
from agentic_workers.core.pause_policy import PauseDecision
from agentic_workers.storage.backend_models import AgentPauseState, SQLModel


@pytest.fixture
def session():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_check_pause_state_returns_false_when_no_record(session):
    """check_pause_state should return False when no pause record exists."""
    assert check_pause_state(session, "firehose") is False


def test_check_pause_state_returns_false_when_not_paused(session):
    """check_pause_state should return False when is_paused=False."""
    pause_state = AgentPauseState(agent_name="firehose", is_paused=False)
    session.add(pause_state)
    session.commit()
    assert check_pause_state(session, "firehose") is False


def test_check_pause_state_returns_true_when_paused(session):
    """check_pause_state should return True when is_paused=True."""
    pause_state = AgentPauseState(agent_name="firehose", is_paused=True)
    session.add(pause_state)
    session.commit()
    assert check_pause_state(session, "firehose") is True


def test_is_agent_paused_alias(session):
    """is_agent_paused should be an alias for check_pause_state."""
    pause_state = AgentPauseState(agent_name="analyst", is_paused=True)
    session.add(pause_state)
    session.commit()
    assert is_agent_paused(session, "analyst") is True


def test_execute_pause_creates_new_record(session):
    """execute_pause should create new pause records."""
    decision = PauseDecision(
        should_pause=True,
        reason="Test pause",
        affected_agents=["firehose", "backfill"],
        resume_condition="Test resume",
    )
    execute_pause(session, decision, triggering_event_id=123)
    session.commit()

    stmt = select(AgentPauseState).where(AgentPauseState.agent_name == "firehose")
    firehose_state = session.exec(stmt).first()
    assert firehose_state is not None
    assert firehose_state.is_paused is True
    assert firehose_state.pause_reason == "Test pause"
    assert firehose_state.triggered_by_event_id == 123


def test_execute_pause_updates_existing_record(session):
    """execute_pause should update existing pause records."""
    # Create initial pause
    pause_state = AgentPauseState(
        agent_name="analyst",
        is_paused=False,
        pause_reason="Old reason",
    )
    session.add(pause_state)
    session.commit()

    # Execute new pause
    decision = PauseDecision(
        should_pause=True,
        reason="New reason",
        affected_agents=["analyst"],
        resume_condition="New condition",
    )
    execute_pause(session, decision, triggering_event_id=456)
    session.commit()

    # Verify update
    stmt = select(AgentPauseState).where(AgentPauseState.agent_name == "analyst")
    updated_state = session.exec(stmt).first()
    assert updated_state.is_paused is True
    assert updated_state.pause_reason == "New reason"
    assert updated_state.triggered_by_event_id == 456
