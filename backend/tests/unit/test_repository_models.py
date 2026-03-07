from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import (
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
)
from app.models.repository import UTCDateTimeType


def test_repository_intake_defaults_cover_queue_baseline() -> None:
    record = RepositoryIntake(
        github_repository_id=123456,
        owner_login="octocat",
        repository_name="hello-world",
        full_name="octocat/hello-world",
    )

    assert record.source_provider == "github"
    assert record.discovery_source is RepositoryDiscoverySource.UNKNOWN
    assert record.firehose_discovery_mode is None
    assert record.queue_status is RepositoryQueueStatus.PENDING
    assert record.discovered_at is not None
    assert record.queue_created_at is not None
    assert record.status_updated_at is not None
    assert record.processing_started_at is None
    assert record.processing_completed_at is None
    assert record.last_failed_at is None
    # Default intake timestamps must be UTC-aware (from _utcnow default_factory)
    assert record.discovered_at.tzinfo == timezone.utc
    assert record.queue_created_at.tzinfo == timezone.utc
    assert record.status_updated_at.tzinfo == timezone.utc


def test_utc_datetime_type_rejects_naive_datetimes() -> None:
    type_instance = UTCDateTimeType()
    with pytest.raises(ValueError, match="timezone-aware"):
        type_instance.process_bind_param(datetime(2026, 3, 7, 12, 0, 0), dialect=None)


def test_utc_datetime_type_accepts_and_normalizes_aware_datetimes() -> None:
    type_instance = UTCDateTimeType()
    aware = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
    result = type_instance.process_bind_param(aware, dialect=None)
    # Result should be naive (tzinfo stripped for SQLite storage) and UTC-equivalent
    assert result is not None
    assert result.tzinfo is None
    assert result == aware.replace(tzinfo=None)


def test_repository_intake_metadata_uses_canonical_identity_and_query_indexes() -> None:
    table = RepositoryIntake.__table__

    assert list(table.primary_key.columns.keys()) == ["github_repository_id"]
    assert table.c.queue_status.type.enums == [status.value for status in RepositoryQueueStatus]
    assert table.c.discovery_source.type.enums == [
        source.value for source in RepositoryDiscoverySource
    ]
    assert table.c.firehose_discovery_mode.type.enums == [
        source.value for source in RepositoryFirehoseMode
    ]
    assert {index.name for index in table.indexes} == {
        "ix_repository_intake_discovery_source",
        "ix_repository_intake_full_name",
        "ix_repository_intake_queue_status",
    }
