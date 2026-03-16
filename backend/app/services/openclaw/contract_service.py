from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from app.core.errors import AppError
from app.schemas.gateway_contract import (
    GitHubApiBudgetSnapshot,
    GatewayAgentIntakeQueueSummary,
    GatewayAgentMonitoringPlaceholder,
    GatewayAgentQueue,
    GatewayAgentQueuePlaceholder,
    GatewayAgentSessionAffinity,
    GatewayAuthorityBoundary,
    GatewayCanonicalInterface,
    GatewayContractResponse,
    GatewayDependencyLink,
    GatewayEventEnvelope,
    GatewayEventEnvelopeField,
    GatewayEventEnvelopeResponse,
    GatewayFrontendBoundary,
    GatewayNamedAgentSummary,
    GatewayRuntimeSurfaceResponse,
    GatewaySessionDetailResponse,
    GatewaySessionHistorySurfaceResponse,
    GatewaySessionAgentContext,
    GatewaySessionSurfaceResponse,
    GatewayTransportTarget,
    NormalizedGatewayHistoryEntry,
    NormalizedGatewayRuntimeState,
    NormalizedGatewaySessionDetail,
    NormalizedGatewaySessionSummary,
)
from app.services.intake_runtime_service import GatewayIntakeRuntimeService
from app.services.openclaw.transport import (
    GatewayTargetResolution,
    map_gateway_transport_error,
    resolve_gateway_target,
)

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "1.2.0"
_QUEUE_PLACEHOLDER_NOTE = (
    "Queue metrics for non-intake agents remain placeholder-only until later monitoring stories."
)
_MONITORING_PLACEHOLDER_NOTE = (
    "Monitoring state will come from Gateway-backed runtime and later worker stories."
)
_INITIAL_AGENT_NOTE = (
    "Named-agent assumptions are explicit in Story 1.3 even before live orchestration exists."
)
_RESERVED_AGENT_NOTE = (
    "This role is reserved for later specialization and is not required to be active in Story 1.3."
)
_AGENT_ROSTER = (
    (
        "overlord",
        "Overlord",
        "control-plane-coordinator",
        "planned",
        "initial",
        "reserved-session-overlord",
        "agent.overlord",
        _INITIAL_AGENT_NOTE,
    ),
    (
        "firehose",
        "Firehose",
        "repository-intake-firehose",
        "planned",
        "initial",
        "reserved-session-firehose",
        "agent.firehose",
        _INITIAL_AGENT_NOTE,
    ),
    (
        "backfill",
        "Backfill",
        "repository-intake-backfill",
        "planned",
        "initial",
        "reserved-session-backfill",
        "agent.backfill",
        _INITIAL_AGENT_NOTE,
    ),
    (
        "bouncer",
        "Bouncer",
        "repository-triage",
        "planned",
        "initial",
        "reserved-session-bouncer",
        "agent.bouncer",
        _INITIAL_AGENT_NOTE,
    ),
    (
        "analyst",
        "Analyst",
        "repository-analysis",
        "planned",
        "initial",
        "reserved-session-analyst",
        "agent.analyst",
        _INITIAL_AGENT_NOTE,
    ),
    (
        "combiner",
        "Combiner",
        "idea-synthesis",
        "reserved",
        "reserved",
        None,
        None,
        _RESERVED_AGENT_NOTE,
    ),
    (
        "obsession",
        "Obsession",
        "idea-tracking",
        "reserved",
        "reserved",
        None,
        None,
        _RESERVED_AGENT_NOTE,
    ),
)


class GatewayContractAdapter(Protocol):
    def resolve_transport_target(self) -> GatewayTargetResolution:
        """Resolve the currently configured Gateway target, if any."""


class SettingsGatewayContractAdapter:
    def resolve_transport_target(self) -> GatewayTargetResolution:
        return resolve_gateway_target()


class GatewayContractService:
    def __init__(
        self,
        adapter: GatewayContractAdapter | None = None,
        intake_runtime_service: GatewayIntakeRuntimeService | None = None,
        runtime_dir: Path | None = None,
    ) -> None:
        self.adapter = adapter or SettingsGatewayContractAdapter()
        self.intake_runtime_service = intake_runtime_service
        self.runtime_dir = runtime_dir

    def get_contract_metadata(self) -> GatewayContractResponse:
        target = self._resolve_target()
        logger.info("Gateway contract metadata resolved: configured=%s", target.configured)
        return GatewayContractResponse(
            contract_version=CONTRACT_VERSION,
            architecture_flow="frontend -> Agentic-Workflow backend -> Gateway",
            runtime_mode="multi-agent",
            named_agents=self._named_agent_summaries(),
            authority_boundary=[
                GatewayAuthorityBoundary(
                    owner="gateway",
                    state_domains=[
                        "session discovery",
                        "session routing context",
                        "control-plane runtime status",
                    ],
                    boundary=(
                        "Gateway remains the canonical source for operator-control-plane "
                        "runtime and session state."
                    ),
                ),
                GatewayAuthorityBoundary(
                    owner="agentic-workflow",
                    state_domains=[
                        "normalized multi-agent API contracts",
                        "repository pipeline data",
                        "analysis artifacts",
                    ],
                    boundary=(
                        "Agentic-Workflow owns app-facing schemas and backend translation "
                        "of Gateway data for multi-agent operator views."
                    ),
                ),
                GatewayAuthorityBoundary(
                    owner="workspace",
                    state_domains=[
                        "checked-out repositories",
                        "project-local runtime artifacts",
                        "diagnostic notes",
                    ],
                    boundary=(
                        "Workspace files provide local context, but they are not the "
                        "primary contract for session or runtime authority."
                    ),
                ),
            ],
            frontend_boundary=GatewayFrontendBoundary(
                flow="frontend -> /api/v1/gateway/* -> Gateway",
                direct_browser_gateway_access=False,
                notes=[
                    "The browser does not call Gateway directly for MVP control-plane reads.",
                    "Future UI stories must consume backend-owned normalized shapes.",
                ],
            ),
            canonical_interfaces=[
                GatewayCanonicalInterface(
                    name="runtime-inspection",
                    canonical_source="Gateway runtime inspection",
                    app_surface="/api/v1/gateway/runtime",
                    contract_status="defined",
                    notes=(
                        "Story 2.6 keeps the runtime mode multi-agent while letting Firehose "
                        "and Backfill expose backend-owned intake summaries."
                    ),
                ),
                GatewayCanonicalInterface(
                    name="session-discovery",
                    canonical_source="Gateway session discovery",
                    app_surface="/api/v1/gateway/sessions",
                    contract_status="defined",
                    notes=(
                        "Story 1.3 keeps session authority with Gateway while making "
                        "agent context explicit on the session contract."
                    ),
                ),
                GatewayCanonicalInterface(
                    name="session-detail-history",
                    canonical_source="Gateway session detail/history",
                    app_surface="/api/v1/gateway/sessions/{session_id}",
                    contract_status="reserved",
                    notes=(
                        "Session detail and history remain Gateway-backed and will stay "
                        "backend-owned when implemented."
                    ),
                ),
                GatewayCanonicalInterface(
                    name="realtime-events",
                    canonical_source="Gateway real-time event stream",
                    app_surface="/api/v1/gateway/events/envelope",
                    contract_status="defined",
                    notes=(
                        "Story 1.2 defines the event envelope now so later streaming work "
                        "does not re-decide the contract."
                    ),
                ),
            ],
            transport_target=self._as_transport_target(target),
            dependency_chain=[
                GatewayDependencyLink(
                    story="1.2",
                    expectation="Defines the Gateway authority boundary and app-owned contract.",
                ),
                GatewayDependencyLink(
                    story="1.3",
                    expectation="Makes the MVP runtime target explicitly multi-agent.",
                ),
                GatewayDependencyLink(
                    story="1.4",
                    expectation="Formalizes configuration ownership for Gateway URL/token sourcing.",
                ),
                GatewayDependencyLink(
                    story="1.5",
                    expectation="Consumes the contract for readiness and connectivity UX.",
                ),
            ],
            constraints=[
                (
                    "Do not treat ~/.openclaw/agents/*/sessions/sessions.json or *.jsonl "
                    "artifacts as the primary system contract."
                ),
                "Any future file-based fallback must be diagnostic-only and opt-in.",
                "Route handlers depend on typed service methods rather than transport helpers.",
                "Multi-agent mode is the explicit MVP target; do not regress to single-agent-only contracts.",
            ],
            event_envelope=self._event_envelope(),
        )

    def get_runtime_surface(self) -> GatewayRuntimeSurfaceResponse:
        try:
            target = self._resolve_target()
            gateway_url = target.url
            logger.debug(
                "Gateway runtime surface: target resolved, configured=%s", target.configured
            )
        except AppError as exc:
            # Story 2.6: Allow runtime inspection to succeed even if gateway transport
            # target resolution fails (e.g. invalid/missing configuration) so that
            # backend-owned intake queues are still rendered.
            if exc.status_code == 422:
                logger.warning(
                    "Gateway target resolution failed (422); runtime surface proceeding without URL"
                )
                gateway_url = None
            else:
                raise

        queue_overrides = (
            self.intake_runtime_service.build_queue_overrides()
            if self.intake_runtime_service is not None
            else None
        )
        return GatewayRuntimeSurfaceResponse(
            contract_version=CONTRACT_VERSION,
            availability="available" if queue_overrides is not None else "reserved",
            runtime=NormalizedGatewayRuntimeState(
                source_of_truth=(
                    "agentic-workflow+gateway" if queue_overrides is not None else "gateway"
                ),
                runtime_mode="multi-agent",
                gateway_url=gateway_url,
                connection_state="reserved",
                status="unknown",
                route_owner="/api/v1/gateway/runtime",
                agent_states=self._named_agent_summaries(queue_overrides=queue_overrides),
                github_api_budget=self._load_github_api_budget(),
                notes=[
                    "The runtime surface keeps Gateway routing metadata and Agentic-Workflow intake data on one backend-owned contract.",
                    "Gateway connectivity does not belong to the generic /health endpoint.",
                ],
            ),
        )

    def get_session_surface(self) -> GatewaySessionSurfaceResponse:
        self._resolve_target()
        return GatewaySessionSurfaceResponse(
            contract_version=CONTRACT_VERSION,
            availability="reserved",
            runtime_mode="multi-agent",
            source_of_truth="gateway",
            named_agents=self._named_agent_summaries(),
            sessions=self._session_placeholders(),
            notes=[
                "Story 1.3 keeps session authority with Gateway while making agent context explicit.",
                "Session lists will stay backend-mediated when population lands in later stories.",
            ],
        )

    def get_session_detail_surface(self, session_id: str) -> GatewaySessionDetailResponse:
        self._resolve_target()
        return GatewaySessionDetailResponse(
            contract_version=CONTRACT_VERSION,
            availability="reserved",
            source_of_truth="gateway",
            session=NormalizedGatewaySessionDetail(
                session_id=session_id,
                label=None,
                route_key=self._reserved_session_detail(session_id).route_key,
                agent_context=self._reserved_session_detail(session_id).agent_context,
                transcript_available=False,
                notes=[
                    "Story 1.3 reserves agent-aware session detail for later Gateway-backed work.",
                ],
            ),
        )

    def get_session_history_surface(
        self,
        session_id: str,
    ) -> GatewaySessionHistorySurfaceResponse:
        self._resolve_target()
        return GatewaySessionHistorySurfaceResponse(
            contract_version=CONTRACT_VERSION,
            availability="reserved",
            source_of_truth="gateway",
            session_id=session_id,
            history=[
                NormalizedGatewayHistoryEntry(
                    entry_id=f"{session_id}:placeholder",
                    role="system",
                    content=None,
                    emitted_at=None,
                )
            ],
            notes=[
                "Story 1.2 publishes the normalized history envelope only.",
                "Later stories will replace this placeholder entry with Gateway-backed data.",
            ],
        )

    def get_event_envelope(self) -> GatewayEventEnvelopeResponse:
        self._resolve_target()
        return GatewayEventEnvelopeResponse(
            contract_version=CONTRACT_VERSION,
            envelope=self._event_envelope(),
        )

    def _resolve_target(self) -> GatewayTargetResolution:
        try:
            return self.adapter.resolve_transport_target()
        except AppError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise map_gateway_transport_error(exc) from exc

    def _load_github_api_budget(self) -> GitHubApiBudgetSnapshot | None:
        if self.runtime_dir is None:
            return None

        snapshot_path = self.runtime_dir / "github" / "quota.json"
        if not snapshot_path.is_file():
            return None

        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.debug("GitHub quota snapshot could not be read.", exc_info=True)
            return None
        if not isinstance(payload, dict):
            return None

        try:
            return GitHubApiBudgetSnapshot.model_validate(payload)
        except Exception:
            logger.debug("GitHub quota snapshot had unexpected shape.", exc_info=True)
            return None

    @staticmethod
    def _as_transport_target(
        target: GatewayTargetResolution,
    ) -> GatewayTransportTarget:
        return GatewayTransportTarget(
            configured=target.configured,
            url=target.url,
            scheme=target.scheme,
            allow_insecure_tls=target.allow_insecure_tls,
            token_configured=target.token_configured,
            source=target.source,
            notes=list(target.notes),
        )

    @staticmethod
    def _named_agent_summaries(
        queue_overrides: dict[str, GatewayAgentIntakeQueueSummary] | None = None,
    ) -> list[GatewayNamedAgentSummary]:
        return [
            GatewayNamedAgentSummary(
                agent_key=agent_key,
                display_name=display_name,
                agent_role=agent_role,
                lifecycle_state=lifecycle_state,
                mvp_scope=mvp_scope,
                queue=GatewayContractService._queue_for_agent(
                    agent_key,
                    queue_overrides=queue_overrides,
                ),
                monitoring=GatewayAgentMonitoringPlaceholder(
                    notes=[_MONITORING_PLACEHOLDER_NOTE],
                ),
                session_affinity=GatewayAgentSessionAffinity(
                    session_id=session_id,
                    route_key=route_key,
                ),
                notes=[note],
            )
            for (
                agent_key,
                display_name,
                agent_role,
                lifecycle_state,
                mvp_scope,
                session_id,
                route_key,
                note,
            ) in _AGENT_ROSTER
        ]

    @staticmethod
    def _queue_for_agent(
        agent_key: str,
        *,
        queue_overrides: dict[str, GatewayAgentIntakeQueueSummary] | None = None,
    ) -> GatewayAgentQueue:
        if queue_overrides is not None and agent_key in queue_overrides:
            return queue_overrides[agent_key]

        return GatewayAgentQueuePlaceholder(
            notes=[_QUEUE_PLACEHOLDER_NOTE],
        )

    @classmethod
    def _session_placeholders(cls) -> list[NormalizedGatewaySessionSummary]:
        return [
            NormalizedGatewaySessionSummary(
                session_id=session_id,
                route_key=route_key,
                agent_context=GatewaySessionAgentContext(
                    agent_key=agent_key,
                    display_name=display_name,
                    agent_role=agent_role,
                ),
            )
            for (
                agent_key,
                display_name,
                agent_role,
                _lifecycle_state,
                mvp_scope,
                session_id,
                route_key,
                _note,
            ) in _AGENT_ROSTER
            if mvp_scope == "initial" and session_id is not None and route_key is not None
        ]

    @classmethod
    def _reserved_session_detail(cls, session_id: str) -> NormalizedGatewaySessionSummary:
        for session in cls._session_placeholders():
            if session.session_id == session_id:
                return session

        return NormalizedGatewaySessionSummary(
            session_id=session_id,
            route_key=None,
            agent_context=None,
        )

    @staticmethod
    def _event_envelope() -> GatewayEventEnvelope:
        return GatewayEventEnvelope(
            version="v1",
            channel="backend-bridge",
            delivery="Gateway stream normalized by Agentic-Workflow backend",
            fields=[
                GatewayEventEnvelopeField(
                    name="event_id",
                    type="string",
                    description="Stable identifier generated by the backend bridge.",
                ),
                GatewayEventEnvelopeField(
                    name="event_type",
                    type="string",
                    description="Normalized Gateway event type consumed by the frontend.",
                ),
                GatewayEventEnvelopeField(
                    name="session_id",
                    type="string | null",
                    description="Associated Gateway session key when the event is session-scoped.",
                ),
                GatewayEventEnvelopeField(
                    name="route_key",
                    type="string | null",
                    description="Normalized routing context for later multi-agent UX.",
                ),
                GatewayEventEnvelopeField(
                    name="occurred_at",
                    type="string",
                    description="ISO-8601 timestamp assigned by the backend bridge.",
                ),
                GatewayEventEnvelopeField(
                    name="payload",
                    type="object",
                    description="Typed event payload owned by the Agentic-Workflow backend.",
                ),
            ],
            notes=[
                "Frontend consumers subscribe to backend-owned events, not raw Gateway frames.",
                "Story 1.2 defines the envelope now; live bridging lands in later stories.",
            ],
        )
