from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_agent_config_service,
    get_backfill_timeline_service,
    get_agent_event_service,
    get_agent_operator_service,
)
from app.core.errors import AppError
from app.schemas.agent_config import (
    AgentName,
    AgentConfigResponse,
    AgentConfigUpdateRequest,
    AgentConfigUpdateResponse,
)
from app.models import AgentRunStatus, EventSeverity, FailureClassification, FailureSeverity
from app.schemas.agent_event import (
    AgentLatestRunsResponse,
    AgentManualRunTriggerResponse,
    AgentPauseStateResponse,
    AgentRunDetailResponse,
    AgentRunListParams,
    AgentRunResponse,
    FailureEventListParams,
    PauseAgentRequest,
    SystemEventListParams,
    SystemEventResponse,
)
from app.schemas.agent_timeline import (
    BackfillTimelineResponse,
    BackfillTimelineUpdateRequest,
    BackfillTimelineUpdateResponse,
)
from app.services.agent_event_service import AgentEventService
from app.services.agent_config_service import AgentConfigService
from app.services.agent_operator_service import AgentOperatorService
from app.services.backfill_timeline_service import BackfillTimelineService

router = APIRouter()


AgentEventServiceDep = Depends(get_agent_event_service)
AgentOperatorServiceDep = Depends(get_agent_operator_service)
AgentConfigServiceDep = Depends(get_agent_config_service)
BackfillTimelineServiceDep = Depends(get_backfill_timeline_service)


def get_agent_run_list_params(
    agent_name: str | None = Query(default=None),
    status: AgentRunStatus | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> AgentRunListParams:
    if since is not None and until is not None and since > until:
        raise AppError(
            message="'since' must not be later than 'until'",
            code="invalid_date_range",
            status_code=400,
        )
    return AgentRunListParams(
        agent_name=(agent_name.strip() or None) if agent_name else None,
        status=status,
        since=since,
        until=until,
        limit=limit,
    )


def get_system_event_list_params(
    agent_name: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    severity: EventSeverity | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> SystemEventListParams:
    if since is not None and until is not None and since > until:
        raise AppError(
            message="'since' must not be later than 'until'",
            code="invalid_date_range",
            status_code=400,
        )
    return SystemEventListParams(
        agent_name=(agent_name.strip() or None) if agent_name else None,
        event_type=(event_type.strip() or None) if event_type else None,
        severity=severity,
        since=since,
        until=until,
        limit=limit,
    )


@router.get("/agents/runs", response_model=list[AgentRunResponse])
def list_agent_runs(
    params: AgentRunListParams = Depends(get_agent_run_list_params),
    service: AgentEventService = AgentEventServiceDep,
) -> list[AgentRunResponse]:
    return service.list_agent_runs(params)


@router.get("/agents/runs/latest", response_model=AgentLatestRunsResponse)
def list_latest_agent_runs(
    service: AgentEventService = AgentEventServiceDep,
) -> AgentLatestRunsResponse:
    return service.get_latest_run_per_agent()


@router.get("/agents/runs/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run_detail(
    run_id: int,
    service: AgentEventService = AgentEventServiceDep,
) -> AgentRunDetailResponse:
    return service.get_agent_run_detail(run_id)


@router.get("/events", response_model=list[SystemEventResponse])
def list_system_events(
    params: SystemEventListParams = Depends(get_system_event_list_params),
    service: AgentEventService = AgentEventServiceDep,
) -> list[SystemEventResponse]:
    return service.list_system_events(params)


def get_failure_event_list_params(
    agent_name: str | None = Query(default=None),
    classification: FailureClassification | None = Query(default=None),
    severity: FailureSeverity | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> FailureEventListParams:
    return FailureEventListParams(
        agent_name=(agent_name.strip() or None) if agent_name else None,
        classification=classification,
        severity=severity,
        since=since,
        limit=limit,
    )


@router.get("/events/failures", response_model=list[SystemEventResponse])
def list_failure_events(
    params: FailureEventListParams = Depends(get_failure_event_list_params),
    service: AgentEventService = AgentEventServiceDep,
) -> list[SystemEventResponse]:
    return service.list_failure_events(params)


@router.get("/agents/pause-state", response_model=list[AgentPauseStateResponse])
def list_agent_pause_states(
    service: AgentEventService = AgentEventServiceDep,
) -> list[AgentPauseStateResponse]:
    return service.list_agent_pause_states()


@router.get("/agents/{agent_name}/pause-state", response_model=AgentPauseStateResponse)
def get_agent_pause_state(
    agent_name: str,
    service: AgentEventService = AgentEventServiceDep,
) -> AgentPauseStateResponse:
    state = service.get_agent_pause_state(agent_name)
    if state is None:
        raise AppError(
            message=f"Agent '{agent_name}' is not a recognised agent name.",
            code="agent_not_found",
            status_code=404,
        )
    return state


@router.post("/agents/{agent_name}/resume", response_model=AgentPauseStateResponse)
def resume_agent(
    agent_name: str,
    service: AgentEventService = AgentEventServiceDep,
) -> AgentPauseStateResponse:
    """Resume a paused agent.

    TODO: Add authentication/authorization before production deployment.
    This endpoint should require operator role and log actual user identity.
    See code review findings: CRITICAL-3
    """
    return service.resume_agent(agent_name)


@router.post("/agents/{agent_name}/pause", response_model=AgentPauseStateResponse)
def pause_agent(
    agent_name: str,
    request: PauseAgentRequest,
    service: AgentEventService = AgentEventServiceDep,
) -> AgentPauseStateResponse:
    """Pause an active agent."""
    return service.pause_agent(agent_name, request.pause_reason, request.resume_condition)


@router.post("/agents/{agent_name}/run", response_model=AgentManualRunTriggerResponse, status_code=202)
def trigger_agent_run(
    agent_name: str,
    service: AgentOperatorService = AgentOperatorServiceDep,
) -> AgentManualRunTriggerResponse:
    return service.trigger_agent_run(agent_name)


@router.get("/agents/{agent_name}/config", response_model=AgentConfigResponse)
def get_agent_config(
    agent_name: AgentName,
    service: AgentConfigService = AgentConfigServiceDep,
) -> AgentConfigResponse:
    return service.get_agent_config(agent_name)


@router.patch("/agents/{agent_name}/config", response_model=AgentConfigUpdateResponse)
def update_agent_config(
    agent_name: AgentName,
    request: AgentConfigUpdateRequest,
    service: AgentConfigService = AgentConfigServiceDep,
) -> AgentConfigUpdateResponse:
    return service.update_agent_config(agent_name, request)


@router.get("/agents/backfill/timeline", response_model=BackfillTimelineResponse)
def get_backfill_timeline(
    service: BackfillTimelineService = BackfillTimelineServiceDep,
) -> BackfillTimelineResponse:
    return service.get_timeline()


@router.patch("/agents/backfill/timeline", response_model=BackfillTimelineUpdateResponse)
def update_backfill_timeline(
    request: BackfillTimelineUpdateRequest,
    service: BackfillTimelineService = BackfillTimelineServiceDep,
) -> BackfillTimelineUpdateResponse:
    return service.update_timeline(request)
