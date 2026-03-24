from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, Enum as SQLEnum, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.schema import Index
from sqlmodel import Field, SQLModel

from app.models.repository import UTCDateTimeType, _enum_values, _utcnow


AGENT_NAMES = (
    "firehose",
    "backfill",
    "bouncer",
    "analyst",
    "overlord",
    "combiner",
    "obsession",
    "idea_scout",
)


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    SKIPPED_PAUSED = "skipped_paused"


class EventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FailureClassification(StrEnum):
    RETRYABLE = "retryable"
    BLOCKING = "blocking"
    RATE_LIMITED = "rate_limited"


class FailureSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ResumedBy(StrEnum):
    AUTO = "auto"
    OPERATOR = "operator"


_AGENT_NAME_SQL = ", ".join(f"'{name}'" for name in AGENT_NAMES)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            f"agent_name IN ({_AGENT_NAME_SQL})",
            name="ck_agent_runs_agent_name_valid",
        ),
        CheckConstraint(
            "items_processed IS NULL OR items_processed >= 0",
            name="ck_agent_runs_items_processed_non_negative",
        ),
        CheckConstraint(
            "items_succeeded IS NULL OR items_succeeded >= 0",
            name="ck_agent_runs_items_succeeded_non_negative",
        ),
        CheckConstraint(
            "items_failed IS NULL OR items_failed >= 0",
            name="ck_agent_runs_items_failed_non_negative",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_agent_runs_duration_non_negative",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_agent_runs_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_agent_runs_output_tokens_non_negative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_agent_runs_total_tokens_non_negative",
        ),
        Index("ix_agent_runs_agent_name", "agent_name"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_started_at", "started_at"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    agent_name: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    status: AgentRunStatus = Field(
        default=AgentRunStatus.RUNNING,
        sa_column=Column(
            SQLEnum(
                AgentRunStatus,
                values_callable=_enum_values,
                name="agent_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'running'"),
        ),
    )
    started_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            UTCDateTimeType(),
            nullable=False,
            server_default=text("(strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))"),
        ),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    duration_seconds: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    items_processed: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    items_succeeded: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    items_failed: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    error_summary: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    error_context: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    provider_name: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
    )
    model_name: str | None = Field(
        default=None,
        sa_column=Column(String(256), nullable=True),
    )
    input_tokens: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    output_tokens: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    total_tokens: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )


class SystemEvent(SQLModel, table=True):
    __tablename__ = "system_events"
    __table_args__ = (
        CheckConstraint(
            f"agent_name IN ({_AGENT_NAME_SQL})",
            name="ck_system_events_agent_name_valid",
        ),
        CheckConstraint("event_type != ''", name="ck_system_events_event_type_not_blank"),
        CheckConstraint("message != ''", name="ck_system_events_message_not_blank"),
        CheckConstraint(
            "upstream_provider IS NULL OR upstream_provider IN ('github', 'llm')",
            name="ck_system_events_upstream_provider_valid",
        ),
        Index("ix_system_events_event_type", "event_type"),
        Index("ix_system_events_agent_name", "agent_name"),
        Index("ix_system_events_created_at", "created_at"),
        Index("ix_system_events_agent_run_id", "agent_run_id"),
        Index("ix_system_events_failure_classification", "failure_classification"),
        Index("ix_system_events_failure_severity", "failure_severity"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(Integer, primary_key=True, autoincrement=True, nullable=False),
    )
    event_type: str = Field(
        sa_column=Column(String(128), nullable=False),
    )
    agent_name: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    severity: EventSeverity = Field(
        default=EventSeverity.INFO,
        sa_column=Column(
            SQLEnum(
                EventSeverity,
                values_callable=_enum_values,
                name="event_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default=text("'info'"),
        ),
    )
    message: str = Field(
        sa_column=Column(Text(), nullable=False),
    )
    context_json: str | None = Field(
        default=None,
        sa_column=Column(Text(), nullable=True),
    )
    agent_run_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
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
    # Failure classification fields — only populated for failure events
    failure_classification: FailureClassification | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                FailureClassification,
                values_callable=_enum_values,
                name="failure_classification",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    failure_severity: FailureSeverity | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                FailureSeverity,
                values_callable=_enum_values,
                name="failure_severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    http_status_code: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    retry_after_seconds: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    affected_repository_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("repository_intake.github_repository_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    upstream_provider: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )


class AgentPauseState(SQLModel, table=True):
    """Tracks pause state for each agent to prevent unsafe processing."""

    __tablename__ = "agent_pause_state"
    __table_args__ = (
        CheckConstraint(
            f"agent_name IN ({_AGENT_NAME_SQL})",
            name="ck_agent_pause_state_agent_name_valid",
        ),
        CheckConstraint(
            "resumed_by IS NULL OR resumed_by IN ('auto', 'operator')",
            name="ck_agent_pause_state_resumed_by_valid",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    agent_name: str = Field(
        sa_column=Column(
            String(64),
            nullable=False,
            unique=True,
            index=True,
        )
    )
    is_paused: bool = Field(default=False, nullable=False)
    paused_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    pause_reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    resume_condition: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    triggered_by_event_id: int | None = Field(
        default=None,
        sa_column=Column(Integer, ForeignKey("system_events.id", ondelete="SET NULL"), nullable=True),
    )
    resumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(UTCDateTimeType(), nullable=True),
    )
    resumed_by: ResumedBy | None = Field(
        default=None,
        sa_column=Column(
            SQLEnum(
                ResumedBy,
                values_callable=_enum_values,
                name="resumed_by",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    version: int = Field(default=1, nullable=False)
