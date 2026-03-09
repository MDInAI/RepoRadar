from fastapi import APIRouter, Depends

from app.api.deps import get_gateway_contract_service
from app.schemas.gateway_contract import (
    GatewayContractResponse,
    GatewayEventEnvelopeResponse,
    GatewayRuntimeSurfaceResponse,
    GatewaySessionDetailResponse,
    GatewaySessionHistorySurfaceResponse,
    GatewaySessionSurfaceResponse,
)
from app.services.openclaw.contract_service import GatewayContractService

router = APIRouter(prefix="/gateway", tags=["gateway"])


ServiceDep = Depends(get_gateway_contract_service)


@router.get("/contract", response_model=GatewayContractResponse)
def read_gateway_contract(
    service: GatewayContractService = ServiceDep,
) -> GatewayContractResponse:
    """Describe the Agentic-Workflow to Gateway integration contract."""
    return service.get_contract_metadata()


@router.get("/runtime", response_model=GatewayRuntimeSurfaceResponse)
def read_gateway_runtime_surface(
    service: GatewayContractService = ServiceDep,
) -> GatewayRuntimeSurfaceResponse:
    """Expose the reserved multi-agent runtime contract surface."""
    return service.get_runtime_surface()


@router.get("/sessions", response_model=GatewaySessionSurfaceResponse)
def read_gateway_sessions_surface(
    service: GatewayContractService = ServiceDep,
) -> GatewaySessionSurfaceResponse:
    """Expose the reserved agent-aware sessions contract surface."""
    return service.get_session_surface()


@router.get("/sessions/{session_id}", response_model=GatewaySessionDetailResponse)
def read_gateway_session_detail_surface(
    session_id: str,
    service: GatewayContractService = ServiceDep,
) -> GatewaySessionDetailResponse:
    """Expose the reserved agent-aware session-detail surface."""
    return service.get_session_detail_surface(session_id)


@router.get(
    "/sessions/{session_id}/history",
    response_model=GatewaySessionHistorySurfaceResponse,
)
def read_gateway_session_history_surface(
    session_id: str,
    service: GatewayContractService = ServiceDep,
) -> GatewaySessionHistorySurfaceResponse:
    """Reserve the normalized session-history surface for later runtime stories."""
    return service.get_session_history_surface(session_id)


@router.get("/events/envelope", response_model=GatewayEventEnvelopeResponse)
def read_gateway_event_envelope(
    service: GatewayContractService = ServiceDep,
) -> GatewayEventEnvelopeResponse:
    """Publish the normalized event envelope the backend will bridge later."""
    return service.get_event_envelope()
