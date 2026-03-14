from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SettingsOwner = Literal["agentic-workflow", "gateway", "openclaw", "workspace"]
SettingsAccess = Literal["project-owned", "read-only-reference", "gateway-managed"]
ValidationSeverity = Literal["error", "warning"]


class ConfigurationOwnership(BaseModel):
    key: str
    owner: SettingsOwner
    access: SettingsAccess
    source: str
    description: str
    surfaces: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MaskedSettingSummary(BaseModel):
    key: str
    label: str
    owner: SettingsOwner
    source: str
    configured: bool
    required: bool
    secret: bool = False
    value: str | None = None
    notes: list[str] = Field(default_factory=list)


class ConfigurationValidationIssue(BaseModel):
    severity: ValidationSeverity
    field: str
    owner: SettingsOwner
    code: str
    message: str
    source: str


class ConfigurationValidationResult(BaseModel):
    valid: bool
    issues: list[ConfigurationValidationIssue] = Field(default_factory=list)


class SettingsSummaryResponse(BaseModel):
    contract_version: str
    ownership: list[ConfigurationOwnership] = Field(default_factory=list)
    project_settings: list[MaskedSettingSummary] = Field(default_factory=list)
    worker_settings: list[MaskedSettingSummary] = Field(default_factory=list)
    openclaw_settings: list[MaskedSettingSummary] = Field(default_factory=list)
    validation: ConfigurationValidationResult


RuntimeHealthStatus = Literal["healthy", "degraded"]


class EventBridgeRuntimeHealthResponse(BaseModel):
    status: RuntimeHealthStatus
    consecutive_failures: int
    last_error: str | None = None
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
    last_event_id: int | None = None
    poll_interval_seconds: float


class EventStreamRuntimeResponse(BaseModel):
    current_subscribers: int
    max_subscribers: int
    subscriber_queue_size: int
    ping_interval_seconds: float


class SettingsRuntimeResponse(BaseModel):
    event_bridge: EventBridgeRuntimeHealthResponse
    event_stream: EventStreamRuntimeResponse
