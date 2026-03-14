"""Tests for synthesis repository persistence and queries."""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel
from app.models.repository import SynthesisRun
from app.repositories.synthesis_repository import SynthesisRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_create_and_get_run(db_session: Session):
    repo = SynthesisRepository(db_session)
    run = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10, 20])

    assert run.id is not None
    assert run.idea_family_id == 1
    assert run.run_type == "combiner"
    assert run.input_repository_ids == [10, 20]

    fetched = repo.get_run(run.id)
    assert fetched is not None
    assert fetched.id == run.id


def test_list_runs_by_family(db_session: Session):
    repo = SynthesisRepository(db_session)
    repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])
    repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[20])
    repo.create_run(idea_family_id=2, run_type="combiner", repository_ids=[30])

    family1_runs = repo.list_runs(idea_family_id=1)
    assert len(family1_runs) == 2

    all_runs = repo.list_runs()
    assert len(all_runs) == 3


def test_update_run_with_parsed_output(db_session: Session):
    repo = SynthesisRepository(db_session)
    run = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])

    updated = repo.update_run_status(
        run.id,
        status="completed",
        output="Full text",
        title="Test Title",
        summary="Test summary",
        key_insights=["A", "B"],
        completed_at=datetime.now(timezone.utc),
    )

    assert updated.status == "completed"
    assert updated.title == "Test Title"
    assert updated.summary == "Test summary"
    assert updated.key_insights == ["A", "B"]


def test_key_insights_round_trip_preserves_none(db_session: Session):
    repo = SynthesisRepository(db_session)
    run = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])

    db_session.commit()
    db_session.expire_all()

    fetched = repo.get_run(run.id)
    assert fetched is not None
    assert fetched.key_insights == []


def test_filter_by_status(db_session: Session):
    repo = SynthesisRepository(db_session)
    run1 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])
    run2 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[20])

    repo.update_run_status(run1.id, status="completed")
    repo.update_run_status(run2.id, status="failed")

    completed = repo.list_runs(status="completed")
    assert len(completed) == 1
    assert completed[0].id == run1.id

    failed = repo.list_runs(status="failed")
    assert len(failed) == 1
    assert failed[0].id == run2.id


def test_search_across_fields(db_session: Session):
    repo = SynthesisRepository(db_session)
    run1 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])
    run2 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[20])
    run3 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[30])

    repo.update_run_status(run1.id, status="completed", title="AI Platform")
    repo.update_run_status(run2.id, status="completed", summary="Building a moat")
    repo.update_run_status(run3.id, status="completed", key_insights=["Unique moat strategy"])

    # Search in title
    results = repo.list_runs(search="platform")
    assert len(results) == 1
    assert results[0].id == run1.id

    # Search in summary
    results = repo.list_runs(search="moat")
    assert len(results) == 2
    assert {r.id for r in results} == {run2.id, run3.id}


def test_filter_by_date_range(db_session: Session):
    repo = SynthesisRepository(db_session)
    now = datetime.now(timezone.utc)

    run1 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10])
    run2 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[20])

    # Manually set created_at for testing
    db_session.query(SynthesisRun).filter(SynthesisRun.id == run1.id).update(
        {"created_at": datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)}
    )
    db_session.query(SynthesisRun).filter(SynthesisRun.id == run2.id).update(
        {"created_at": datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)}
    )
    db_session.commit()

    # Filter from March 10
    results = repo.list_runs(date_from=datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc))
    assert len(results) == 1
    assert results[0].id == run2.id

    # Filter to March 10
    results = repo.list_runs(date_to=datetime(2026, 3, 10, 23, 59, 59, tzinfo=timezone.utc))
    assert len(results) == 1
    assert results[0].id == run1.id


def test_filter_by_repository(db_session: Session):
    repo = SynthesisRepository(db_session)
    run1 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[10, 20])
    run2 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[20, 30])
    run3 = repo.create_run(idea_family_id=1, run_type="combiner", repository_ids=[40])

    # Filter by repo 20 - should match run1 and run2
    results = repo.list_runs(repository_id=20)
    assert len(results) == 2
    assert {r.id for r in results} == {run1.id, run2.id}

    # Filter by repo 10 - should match only run1
    results = repo.list_runs(repository_id=10)
    assert len(results) == 1
    assert results[0].id == run1.id

    # Filter by repo 40 - should match only run3
    results = repo.list_runs(repository_id=40)
    assert len(results) == 1
    assert results[0].id == run3.id
