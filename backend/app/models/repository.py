from __future__ import annotations

import json
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
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.mutable import MutableDict, MutableList
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


class JSONStringListType(TypeDecorator):
    """Persist small string lists as JSON-encoded text across SQLite and Postgres."""

    impl = Text
    cache_ok = True

    def process_bind_param(
        self,
        value: list[str] | tuple[str, ...] | None,
        dialect: Dialect,
    ) -> str:
        items = [] if value is None else list(value)
        if any(not isinstance(item, str) for item in items):
            raise ValueError("JSONStringListType accepts only string items")
        return json.dumps(items)

    def process_result_value(self, value: str | None, dialect: Dialect) -> list[str]:
        if value is None:
            return []
        decoded = json.loads(value)
        if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
            raise ValueError("JSONStringListType stored value must decode to list[str]")
        return decoded


class JSONStringDictType(TypeDecorator):
    """Persist small JSON objects as text across SQLite and Postgres."""

    impl = Text
    cache_ok = True

    def process_bind_param(
        self,
        value: dict[str, object] | None,
        dialect: Dialect,
    ) -> str | None:
        if value is None:
            return None
        payload = value
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise ValueError("JSONStringDictType accepts only dict[str, object]")
        return json.dumps(payload, sort_keys=True)

    def process_result_value(self, value: str | None, dialect: Dialect) -> dict[str, object] | None:
        if value is None:
            return None
        decoded = json.loads(value)
        if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
            raise ValueError("JSONStringDictType stored value must decode to dict[str, object]")
        return decoded


class JSONIntListType(TypeDecorator):
    """Persist integer lists as JSON-encoded text across SQLite and Postgres."""

    impl = Text
    cache_ok = True

    def process_bind_param(
        self,
        value: list[int] | tuple[int, ...] | None,
        dialect: Dialect,
    ) -> str:
        items = [] if value is None else list(value)
        if any(not isinstance(item, int) for item in items):
            raise ValueError("JSONIntListType accepts only integer items")
        return json.dumps(items)

    def process_result_value(self, value: str | None, dialect: Dialect) -> list[int]:
        if value is None:
            return []
        decoded = json.loads(value)
        if not isinstance(decoded, list) or any(not isinstance(item, int) for item in decoded):
            raise ValueError("JSONIntListType stored value must decode to list[int]")
        return decoded


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


class RepositoryTriageStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RepositoryTriageExplanationKind(StrEnum):
    EXCLUDE_RULE = "exclude_rule"
    INCLUDE_RULE = "include_rule"
    ALLOWLIST_MISS = "allowlist_miss"
    PASS_THROUGH = "pass_through"


class RepositoryAnalysisStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RepositoryAnalysisFailureCode(StrEnum):
    TRANSPORT_ERROR = "transport_error"
    RATE_LIMITED = "rate_limited"
    MISSING_README = "missing_readme"
    INVALID_README_PAYLOAD = "invalid_readme_payload"
    INVALID_ANALYSIS_OUTPUT = "invalid_analysis_output"
    PERSISTENCE_ERROR = "persistence_error"


class RepositoryMonetizationPotential(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepositoryCategory(StrEnum):
    WORKFLOW = "workflow"
    ANALYTICS = "analytics"
    DEVOPS = "devops"
    INFRASTRUCTURE = "infrastructure"
    DEVTOOLS = "devtools"
    CRM = "crm"
    COMMUNICATION = "communication"
    SUPPORT = "support"
    OBSERVABILITY = "observability"
    LOW_CODE = "low_code"
    SECURITY = "security"
    AI_ML = "ai_ml"
    DATA = "data"
    PRODUCTIVITY = "productivity"


class RepositoryIntake(SQLModel, table=True):
    __tablename__ = "repository_intake"
    __table_args__ = (
        CheckConstraint(
            "source_provider IN ('github')", name="ck_repository_intake_source_provider_valid"
        ),
        CheckConstraint("owner_login != ''", name="ck_repository_intake_owner_login_not_blank"),
        CheckConstraint(
            "repository_name != ''", name="ck_repository_intake_repository_name_not_blank"
        ),
        CheckConstraint("full_name != ''", name="ck_repository_intake_full_name_not_blank"),
        CheckConstraint("stargazers_count >= 0", name="ck_repository_intake_stars_non_negative"),
        CheckConstraint("forks_count >= 0", name="ck_repository_intake_forks_non_negative"),
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
        Index("ix_repository_intake_triage_status", "triage_status"),
        Index("ix_repository_intake_analysis_status", "analysis_status"),
        Index("ix_repository_intake_pushed_at", "pushed_at"),
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
    repository_description: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    stargazers_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    forks_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    github_created_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    pushed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
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
    triage_status: RepositoryTriageStatus = Field(
        default=RepositoryTriageStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                RepositoryTriageStatus,
                values_callable=_enum_values,
                name="repository_triage_status",
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
    triaged_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    analysis_status: RepositoryAnalysisStatus = Field(
        default=RepositoryAnalysisStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                RepositoryAnalysisStatus,
                values_callable=_enum_values,
                name="repository_analysis_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'pending'"),
        ),
    )
    analysis_started_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    analysis_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    analysis_last_attempted_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    analysis_last_failed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    analysis_failure_code: RepositoryAnalysisFailureCode | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                RepositoryAnalysisFailureCode,
                values_callable=_enum_values,
                name="repository_analysis_failure_code",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    analysis_failure_message: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )


class RepositoryUserCuration(SQLModel, table=True):
    __tablename__ = "repository_user_curation"
    __table_args__ = (
        Index("ix_repository_user_curation_is_starred", "is_starred"),
    )

    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    is_starred: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("0"),
        ),
    )
    starred_at: datetime | None = Field(
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


class RepositoryUserTag(SQLModel, table=True):
    __tablename__ = "repository_user_tag"
    __table_args__ = (
        CheckConstraint("tag_label != ''", name="ck_repository_user_tag_label_not_blank"),
        Index("ix_repository_user_tag_github_repository_id", "github_repository_id"),
        UniqueConstraint(
            "github_repository_id",
            "tag_label",
            name="uq_repository_user_tag_github_repository_id_tag_label",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    tag_label: str = Field(
        sa_column=Column(String(100), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class IdeaFamily(SQLModel, table=True):
    __tablename__ = "idea_family"
    __table_args__ = (
        CheckConstraint("title != ''", name="ck_idea_family_title_not_blank"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    title: str = Field(
        sa_column=Column(String(200), nullable=False),
    )
    description: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class IdeaFamilyMembership(SQLModel, table=True):
    __tablename__ = "idea_family_membership"
    __table_args__ = (
        Index("ix_idea_family_membership_idea_family_id", "idea_family_id"),
        Index("ix_idea_family_membership_github_repository_id", "github_repository_id"),
        UniqueConstraint(
            "idea_family_id",
            "github_repository_id",
            name="uq_idea_family_membership_idea_family_id_github_repository_id",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    idea_family_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("idea_family.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    added_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class ObsessionRefreshPolicy(StrEnum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class ObsessionContextStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class ObsessionContext(SQLModel, table=True):
    __tablename__ = "obsession_context"
    __table_args__ = (
        CheckConstraint("title != ''", name="ck_obsession_context_title_not_blank"),
        CheckConstraint(
            "(idea_family_id IS NOT NULL AND synthesis_run_id IS NULL) OR "
            "(idea_family_id IS NULL AND synthesis_run_id IS NOT NULL)",
            name="ck_obsession_context_exactly_one_target",
        ),
        Index("ix_obsession_context_idea_family_id", "idea_family_id"),
        Index("ix_obsession_context_synthesis_run_id", "synthesis_run_id"),
        Index("ix_obsession_context_status", "status"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    idea_family_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("idea_family.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    synthesis_run_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("synthesis_run.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    title: str = Field(
        sa_column=Column(String(200), nullable=False),
    )
    description: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    status: ObsessionContextStatus = Field(
        default=ObsessionContextStatus.ACTIVE,
        sa_column=Column(
            SQLEnum(
                ObsessionContextStatus,
                values_callable=_enum_values,
                name="obsession_context_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'active'"),
        ),
    )
    refresh_policy: ObsessionRefreshPolicy = Field(
        default=ObsessionRefreshPolicy.MANUAL,
        sa_column=Column(
            SQLEnum(
                ObsessionRefreshPolicy,
                values_callable=_enum_values,
                name="obsession_refresh_policy",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'manual'"),
        ),
    )
    last_refresh_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class AgentMemorySegment(SQLModel, table=True):
    __tablename__ = "agent_memory_segments"
    __table_args__ = (
        CheckConstraint("segment_key != ''", name="ck_agent_memory_segment_key_not_blank"),
        CheckConstraint("content != ''", name="ck_agent_memory_content_not_blank"),
        CheckConstraint("content_type IN ('markdown', 'json')", name="ck_agent_memory_content_type_enum"),
        CheckConstraint("length(content) <= 51200", name="ck_agent_memory_content_size"),
        UniqueConstraint(
            "obsession_context_id",
            "segment_key",
            name="uq_agent_memory_segments_obsession_context_id_segment_key",
        ),
        Index("ix_agent_memory_segments_obsession_context_id", "obsession_context_id"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    obsession_context_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("obsession_context.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    segment_key: str = Field(
        sa_column=Column(String(100), nullable=False),
    )
    content: str = Field(
        sa_column=Column(Text, nullable=False),
    )
    content_type: str = Field(
        default="markdown",
        sa_column=Column(
            String(32),
            nullable=False,
            server_default=text("'markdown'"),
        ),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class SynthesisRunType(StrEnum):
    COMBINER = "combiner"
    OBSESSION = "obsession"


class SynthesisRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SynthesisRun(SQLModel, table=True):
    __tablename__ = "synthesis_run"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('combiner', 'obsession')",
            name="ck_synthesis_run_type_valid",
        ),
        Index("ix_synthesis_run_idea_family_id", "idea_family_id"),
        Index("ix_synthesis_run_status", "status"),
        Index("ix_synthesis_run_obsession_context_id", "obsession_context_id"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    idea_family_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("idea_family.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    obsession_context_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("obsession_context.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    run_type: SynthesisRunType = Field(
        sa_column=Column(
            SQLEnum(
                SynthesisRunType,
                values_callable=_enum_values,
                name="synthesis_run_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
    )
    status: SynthesisRunStatus = Field(
        default=SynthesisRunStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                SynthesisRunStatus,
                values_callable=_enum_values,
                name="synthesis_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'pending'"),
        ),
    )
    input_repository_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONIntListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    output_text: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    title: str | None = Field(
        default=None,
        sa_column=Column(String(500), nullable=True),
    )
    summary: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    key_insights: list[str] | None = Field(
        default=None,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=True,
        ),
    )
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )


class RepositoryTriageExplanation(SQLModel, table=True):
    __tablename__ = "repository_triage_explanation"
    __table_args__ = (
        CheckConstraint(
            "explanation_summary != ''",
            name="ck_repository_triage_explanation_summary_not_blank",
        ),
    )

    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    explanation_kind: RepositoryTriageExplanationKind = Field(
        sa_column=Column(
            SQLEnum(
                RepositoryTriageExplanationKind,
                values_callable=_enum_values,
                name="repository_triage_explanation_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
    )
    explanation_summary: str = Field(
        sa_column=Column(Text(), nullable=False),
    )
    matched_include_rules: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    matched_exclude_rules: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    explained_at: datetime = Field(
        sa_column=Column(UTCDateTimeType(), nullable=False),
    )
    triage_logic_version: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )
    triage_config_fingerprint: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )


class RepositoryAnalysisResult(SQLModel, table=True):
    __tablename__ = "repository_analysis_result"
    __table_args__ = (
        CheckConstraint(
            "source_provider IN ('github')",
            name="ck_repository_analysis_result_source_provider_valid",
        ),
        CheckConstraint(
            "source_kind != ''", name="ck_repository_analysis_result_source_kind_not_blank"
        ),
    )

    github_repository_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("repository_intake.github_repository_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    source_provider: str = Field(
        default="github",
        sa_column=Column(
            String(32),
            nullable=False,
            server_default=text("'github'"),
        ),
    )
    source_kind: str = Field(
        default="repository_readme",
        sa_column=Column(
            String(64),
            nullable=False,
            server_default=text("'repository_readme'"),
        ),
    )
    source_metadata: dict[str, object] = Field(
        default_factory=dict,
        sa_column=Column(
            MutableDict.as_mutable(JSONStringDictType()),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    monetization_potential: RepositoryMonetizationPotential = Field(
        sa_column=Column(
            SQLEnum(
                RepositoryMonetizationPotential,
                values_callable=_enum_values,
                name="repository_monetization_potential",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
    )
    category: RepositoryCategory | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                RepositoryCategory,
                values_callable=_enum_values,
                name="repository_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    agent_tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    suggested_new_categories: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    suggested_new_tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    pros: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    cons: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    missing_feature_signals: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            MutableList.as_mutable(JSONStringListType()),
            nullable=False,
            server_default=text("'[]'"),
        ),
    )
    category_confidence_score: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    problem_statement: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    target_customer: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    product_type: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    business_model_guess: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    technical_stack: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    target_audience: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    open_problems: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    competitors: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    confidence_score: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    recommended_action: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    analyzed_at: datetime = Field(
        sa_column=Column(UTCDateTimeType(), nullable=False),
    )


class BackfillProgress(SQLModel, table=True):
    __tablename__ = "backfill_progress"
    __table_args__ = (
        CheckConstraint(
            "source_provider IN ('github')", name="ck_backfill_progress_source_provider_valid"
        ),
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
    pages_processed_in_run: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    exhausted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("0")),
    )
    resume_required: bool = Field(
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


class FirehoseProgress(SQLModel, table=True):
    __tablename__ = "firehose_progress"
    __table_args__ = (
        CheckConstraint(
            "source_provider IN ('github')", name="ck_firehose_progress_source_provider_valid"
        ),
        CheckConstraint("next_page > 0", name="ck_firehose_progress_next_page_positive"),
        CheckConstraint(
            "(resume_required = 0) OR ("
            "active_mode IS NOT NULL AND "
            "new_anchor_date IS NOT NULL AND "
            "trending_anchor_date IS NOT NULL AND "
            "run_started_at IS NOT NULL"
            ")",
            name="ck_firehose_progress_resume_state_complete",
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
    active_mode: RepositoryFirehoseMode | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                RepositoryFirehoseMode,
                values_callable=_enum_values,
                name="firehose_progress_mode",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    next_page: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default=text("1")),
    )
    pages_processed_in_run: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    new_anchor_date: date | None = Field(
        default=None,
        sa_column=Column(Date(), nullable=True),
    )
    trending_anchor_date: date | None = Field(
        default=None,
        sa_column=Column(Date(), nullable=True),
    )
    run_started_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    resume_required: bool = Field(
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
