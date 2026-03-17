from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import EventSeverity

OverlordSystemStatus = Literal[
    "healthy",
    "degraded",
    "blocked",
    "rate-limited",
    "operator-required",
    "auto-recovering",
    "stale-state-mismatch",
]
OverlordIncidentStatus = Literal["active", "resolved"]
OverlordRemediationAction = Literal[
    "safe_pause",
    "safe_resume",
    "safe_retry",
    "stale_state_cleanup",
    "resolved_alert_cleanup",
    "cooldown_aware_retry_scheduling",
    "notify",
]


class OverlordIncident(BaseModel):
    incident_key: str
    title: str
    status: OverlordIncidentStatus = "active"
    system_status: OverlordSystemStatus
    severity: EventSeverity
    summary: str
    agent_name: str | None = None
    provider: str | None = None
    detected_at: datetime | None = None
    last_observed_at: datetime | None = None
    retry_after_seconds: int | None = None
    requires_operator: bool = False
    auto_recovering: bool = False
    why_it_happened: str
    what_overlord_did: str | None = None
    operator_action: str | None = None


class OverlordActionRecord(BaseModel):
    action: OverlordRemediationAction
    target: str
    summary: str
    created_at: datetime | None = None
    status: Literal["applied", "skipped", "resolved"]


class OverlordTelegramStatus(BaseModel):
    enabled: bool
    min_severity: EventSeverity = EventSeverity.ERROR
    daily_digest_enabled: bool = False
    configured_chat: bool = False
    configured_token: bool = False


class OverlordSummaryResponse(BaseModel):
    agent_name: str = "overlord"
    display_name: str = "Overlord"
    status: OverlordSystemStatus
    headline: str
    summary: str
    generated_at: datetime
    incidents: list[OverlordIncident] = Field(default_factory=list)
    recent_actions: list[OverlordActionRecord] = Field(default_factory=list)
    operator_todos: list[str] = Field(default_factory=list)
    telemetry: dict[str, int | str | bool | None] = Field(default_factory=dict)
    telegram: OverlordTelegramStatus


class OverlordPolicyResponse(BaseModel):
    auto_remediation_enabled: bool
    safe_pause_enabled: bool
    safe_resume_enabled: bool
    stale_state_cleanup_enabled: bool
    telegram: OverlordTelegramStatus
