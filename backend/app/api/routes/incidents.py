from fastapi import APIRouter, Depends

from app.api.deps import get_agent_event_service
from app.core.errors import AppError
from app.schemas.incident import IncidentListParams, IncidentResponse
from app.services.agent_event_service import AgentEventService

router = APIRouter()


@router.get("/incidents", response_model=list[IncidentResponse])
def list_incidents(
    params: IncidentListParams = Depends(),
    service: AgentEventService = Depends(get_agent_event_service),
) -> list[IncidentResponse]:
    return service.list_incidents(params)


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: int,
    service: AgentEventService = Depends(get_agent_event_service),
) -> IncidentResponse:
    incident = service.get_incident(incident_id)
    if incident is None:
        raise AppError(
            message=f"Incident {incident_id} not found",
            code="incident_not_found",
            status_code=404,
        )
    return incident
