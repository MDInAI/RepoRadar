from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    Integer,
    String,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import Index
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class UTCDateTimeType(TypeDecorator):
    """DateTime TypeDecorator that enforces UTC-aware datetimes on write and read.

    On write: raises ValueError for naive datetimes so callers cannot silently
    persist local timestamps that will be relabelled as UTC on readback.
    On read: restores timezone.utc since SQLite's DateTime dialect strips tzinfo.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"UTCDateTimeType requires a timezone-aware datetime; "
                f"got naive datetime {value!r}. Pass datetime.now(timezone.utc) instead."
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class RepositoryDiscoverySource(StrEnum):
    UNKNOWN = "unknown"
    FIREHOSE = "firehose"
    BACKFILL = "backfill"


class RepositoryFirehoseMode(StrEnum):
    NEW = "new"
    TRENDING = "trending"


class RepositoryQueueStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RepositoryIntake(SQLModel, table=True):
    __tablename__ = "repository_intake"
    __table_args__ = (
        CheckConstraint("source_provider IN ('github')", name="ck_repository_intake_source_provider_valid"),
        CheckConstraint("owner_login != ''", name="ck_repository_intake_owner_login_not_blank"),
        CheckConstraint("repository_name != ''", name="ck_repository_intake_repository_name_not_blank"),
        CheckConstraint("full_name != ''", name="ck_repository_intake_full_name_not_blank"),
        CheckConstraint(
            "full_name = owner_login || '/' || repository_name",
            name="ck_repository_intake_full_name_consistent",
        ),
        CheckConstraint(
            "("
            "discovery_source = 'firehose' AND firehose_discovery_mode IS NOT NULL"
            ") OR ("
            "discovery_source != 'firehose' AND firehose_discovery_mode IS NULL"
            ")",
            name="ck_repository_intake_firehose_mode_matches_discovery_source",
        ),
        Index("ix_repository_intake_discovery_source", "discovery_source"),
        Index("ix_repository_intake_full_name", "full_name"),
        Index("ix_repository_intake_queue_status", "queue_status"),
    )

    github_repository_id: int = Field(
        sa_column=Column(BigInteger, primary_key=True, nullable=False),
    )
    source_provider: str = Field(
        default="github",
        sa_column=Column(
            String(32),
            nullable=False,
            server_default=text("'github'"),
        ),
    )
    owner_login: str = Field(
        sa_column=Column(String(255), nullable=False),
    )
    repository_name: str = Field(
        sa_column=Column(String(255), nullable=False),
    )
    full_name: str = Field(
        sa_column=Column(String(511), nullable=False),
    )
    discovery_source: RepositoryDiscoverySource = Field(
        default=RepositoryDiscoverySource.UNKNOWN,
        sa_column=Column(
            SQLEnum(
                RepositoryDiscoverySource,
                values_callable=_enum_values,
                name="repository_discovery_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'unknown'"),
        ),
    )
    firehose_discovery_mode: RepositoryFirehoseMode | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                RepositoryFirehoseMode,
                values_callable=_enum_values,
                name="repository_firehose_mode",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    queue_status: RepositoryQueueStatus = Field(
        default=RepositoryQueueStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                RepositoryQueueStatus,
                values_callable=_enum_values,
                name="repository_queue_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'pending'"),
        ),
    )
    discovered_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    queue_created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    status_updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    processing_started_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    processing_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    last_failed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )


class BackfillProgress(SQLModel, table=True):
    __tablename__ = "backfill_progress"
    __table_args__ = (
        CheckConstraint("source_provider IN ('github')", name="ck_backfill_progress_source_provider_valid"),
        CheckConstraint("next_page > 0", name="ck_backfill_progress_next_page_positive"),
        CheckConstraint(
            "window_start_date < created_before_boundary",
            name="ck_backfill_progress_window_before_boundary",
        ),
    )

    source_provider: str = Field(
        default="github",
        sa_column=Column(
            String(32),
            primary_key=True,
            nullable=False,
            server_default=text("'github'"),
        ),
    )
    window_start_date: date = Field(
        sa_column=Column(Date(), nullable=False),
    )
    created_before_boundary: date = Field(
        sa_column=Column(Date(), nullable=False),
    )
    created_before_cursor: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    next_page: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    exhausted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("0")),
    )
    last_checkpointed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


def exhausted_backfill_boundary(min_created_date: date) -> date:
    return min_created_date + timedelta(days=1)
