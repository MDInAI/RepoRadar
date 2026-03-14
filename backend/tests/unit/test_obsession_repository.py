import pytest
from datetime import datetime, timezone

from app.repositories.obsession_repository import ObsessionRepository
from app.models.repository import ObsessionContext, IdeaFamily


def test_create_context(session):
    family = IdeaFamily(title="Test Family", description="Test")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    context = repo.create_context(
        idea_family_id=family.id,
        title="Test Context",
        description="Test description",
        refresh_policy="manual",
    )

    assert context.id is not None
    assert context.idea_family_id == family.id
    assert context.title == "Test Context"
    assert context.description == "Test description"
    assert context.status == "active"
    assert context.refresh_policy == "manual"
    assert context.last_refresh_at is None


def test_get_context(session):
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    created = repo.create_context(
        title="Test",
        description=None,
        refresh_policy="daily",
        idea_family_id=family.id,
    )

    fetched = repo.get_context(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "Test"
    assert fetched.refresh_policy == "daily"


def test_get_context_not_found(session):
    repo = ObsessionRepository(session)
    result = repo.get_context(99999)
    assert result is None


def test_list_contexts(session):
    family1 = IdeaFamily(title="Family 1")
    family2 = IdeaFamily(title="Family 2")
    session.add_all([family1, family2])
    session.flush()

    repo = ObsessionRepository(session)
    ctx1 = repo.create_context(title="Context 1", description=None, refresh_policy="manual", idea_family_id=family1.id)
    ctx2 = repo.create_context(title="Context 2", description=None, refresh_policy="daily", idea_family_id=family2.id)

    all_contexts = repo.list_contexts(None, None)
    assert len(all_contexts) == 2

    family1_contexts = repo.list_contexts(family1.id, None)
    assert len(family1_contexts) == 1
    assert family1_contexts[0].id == ctx1.id


def test_list_contexts_by_status(session):
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    ctx1 = repo.create_context(title="Active", description=None, refresh_policy="manual", idea_family_id=family.id)
    ctx2 = repo.create_context(title="Paused", description=None, refresh_policy="manual", idea_family_id=family.id)
    repo.update_context(ctx2.id, None, ..., "paused", None)

    active = repo.list_contexts(None, "active")
    assert len(active) == 1
    assert active[0].id == ctx1.id

    paused = repo.list_contexts(None, "paused")
    assert len(paused) == 1
    assert paused[0].id == ctx2.id


def test_update_context(session):
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    context = repo.create_context(title="Original", description="Desc", refresh_policy="manual", idea_family_id=family.id)

    updated = repo.update_context(context.id, "Updated", ..., "paused", "daily")
    assert updated.title == "Updated"
    assert updated.description == "Desc"
    assert updated.status == "paused"
    assert updated.refresh_policy == "daily"


def test_update_context_clear_description(session):
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    context = repo.create_context(title="Test", description="Description", refresh_policy="manual", idea_family_id=family.id)

    updated = repo.update_context(context.id, None, None, None, None)
    assert updated.description is None


def test_update_context_not_found(session):
    repo = ObsessionRepository(session)
    with pytest.raises(Exception) as exc:
        repo.update_context(99999, "New Title", ..., None, None)
    assert "not found" in str(exc.value).lower()


def test_update_last_refresh(session):
    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    context = repo.create_context(title="Test", description=None, refresh_policy="manual", idea_family_id=family.id)
    assert context.last_refresh_at is None

    updated = repo.update_last_refresh(context.id)
    assert updated.last_refresh_at is not None
    assert isinstance(updated.last_refresh_at, datetime)


def test_get_synthesis_run_count(session):
    from app.models.repository import SynthesisRun

    family = IdeaFamily(title="Test Family")
    session.add(family)
    session.flush()

    repo = ObsessionRepository(session)
    context = repo.create_context(title="Test", description=None, refresh_policy="manual", idea_family_id=family.id)

    count = repo.get_synthesis_run_count(context.id)
    assert count == 0

    run = SynthesisRun(
        idea_family_id=family.id,
        obsession_context_id=context.id,
        run_type="obsession",
        input_repository_ids=[],
    )
    session.add(run)
    session.flush()

    count = repo.get_synthesis_run_count(context.id)
    assert count == 1
