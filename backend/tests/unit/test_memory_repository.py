import pytest
from datetime import datetime
from sqlmodel import Session

from app.models.repository import AgentMemorySegment, ObsessionContext, IdeaFamily
from app.repositories.memory_repository import MemoryRepository


@pytest.fixture
def idea_family(session: Session) -> IdeaFamily:
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.commit()
    session.refresh(family)
    return family


@pytest.fixture
def obsession_context(session: Session, idea_family: IdeaFamily) -> ObsessionContext:
    context = ObsessionContext(
        title="Test Context",
        idea_family_id=idea_family.id,
    )
    session.add(context)
    session.commit()
    session.refresh(context)
    return context


def test_write_segment_creates_new(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    result = repo.write_segment(
        obsession_context_id=obsession_context.id,
        segment_key="insights",
        content="Test insights content",
        content_type="markdown",
    )

    assert result.id is not None
    assert result.segment_key == "insights"
    assert result.content == "Test insights content"
    assert result.content_type == "markdown"
    assert isinstance(result.created_at, datetime)
    assert isinstance(result.updated_at, datetime)


def test_write_segment_updates_existing(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    first = repo.write_segment(
        obsession_context_id=obsession_context.id,
        segment_key="patterns",
        content="Original content",
        content_type="markdown",
    )

    second = repo.write_segment(
        obsession_context_id=obsession_context.id,
        segment_key="patterns",
        content="Updated content",
        content_type="json",
    )

    assert first.id == second.id
    assert second.content == "Updated content"
    assert second.content_type == "json"
    assert second.updated_at > first.updated_at


def test_read_segment_returns_existing(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    repo.write_segment(
        obsession_context_id=obsession_context.id,
        segment_key="next_steps",
        content="Step 1, Step 2",
        content_type="markdown",
    )

    result = repo.read_segment(obsession_context.id, "next_steps")

    assert result is not None
    assert result.segment_key == "next_steps"
    assert result.content == "Step 1, Step 2"


def test_read_segment_returns_none_when_not_found(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    result = repo.read_segment(obsession_context.id, "nonexistent")

    assert result is None


def test_list_segments_returns_all(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    repo.write_segment(obsession_context.id, "insights", "Content 1", "markdown")
    repo.write_segment(obsession_context.id, "patterns", "Content 2", "json")
    repo.write_segment(obsession_context.id, "next_steps", "Content 3", "markdown")

    results = repo.list_segments(obsession_context.id)

    assert len(results) == 3
    assert {r.segment_key for r in results} == {"insights", "patterns", "next_steps"}


def test_list_segments_returns_empty_when_none(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    results = repo.list_segments(obsession_context.id)

    assert results == []


def test_delete_segment_removes_existing(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    repo.write_segment(obsession_context.id, "temp", "Temporary", "markdown")

    deleted = repo.delete_segment(obsession_context.id, "temp")
    assert deleted is True

    result = repo.read_segment(obsession_context.id, "temp")
    assert result is None


def test_delete_segment_returns_false_when_not_found(session: Session, obsession_context: ObsessionContext):
    repo = MemoryRepository(session)

    deleted = repo.delete_segment(obsession_context.id, "nonexistent")

    assert deleted is False


def test_unique_constraint_per_context(session: Session, idea_family: IdeaFamily):
    context1 = ObsessionContext(title="Context 1", idea_family_id=idea_family.id)
    context2 = ObsessionContext(title="Context 2", idea_family_id=idea_family.id)
    session.add_all([context1, context2])
    session.commit()
    session.refresh(context1)
    session.refresh(context2)

    repo = MemoryRepository(session)

    seg1 = repo.write_segment(context1.id, "shared_key", "Content 1", "markdown")
    seg2 = repo.write_segment(context2.id, "shared_key", "Content 2", "markdown")

    assert seg1.id != seg2.id
    assert seg1.content == "Content 1"
    assert seg2.content == "Content 2"
