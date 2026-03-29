from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urlerror
from urllib import parse, request

from sqlmodel import Session

from app.models import EventSeverity, ResumedBy
from app.repositories.agent_event_repository import AgentEventRepository, AgentRunListFilters, SystemEventListFilters
from app.schemas.gateway_contract import GeminiApiKeyPoolSnapshot, GitHubApiBudgetSnapshot
from app.schemas.overlord import (
    OverlordActionRecord,
    OverlordIncident,
    OverlordPolicyResponse,
    OverlordSummaryResponse,
    OverlordTelegramStatus,
)
from app.services.openclaw.contract_service import GatewayContractService
from app.services.overview_service import OverviewService


@dataclass(slots=True)
class OverlordSettings:
    auto_remediation_enabled: bool = True
    safe_pause_enabled: bool = True
    safe_resume_enabled: bool = True
    stale_state_cleanup_enabled: bool = True
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_min_severity: EventSeverity = EventSeverity.ERROR
    telegram_daily_digest_enabled: bool = False
    evaluation_interval_seconds: int = 60


class OverlordStateStore:
    def __init__(self, runtime_dir: Path | None) -> None:
        root = runtime_dir or Path("../runtime")
        self.path = Path(root) / "state" / "overlord-state.json"

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"active_incidents": {}, "telegram": {}, "daily_digest": {}}
        except json.JSONDecodeError:
            return {"active_incidents": {}, "telegram": {}, "daily_digest": {}}

    def save(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))


class OverlordService:
    def __init__(
        self,
        session: Session,
        gateway_contract_service: GatewayContractService,
        settings: OverlordSettings,
        runtime_dir: Path | None = None,
    ) -> None:
        self.session = session
        self.repository = AgentEventRepository(session, runtime_dir=runtime_dir)
        self.overview_service = OverviewService(session)
        self.gateway_contract_service = gateway_contract_service
        self.settings = settings
        self.state_store = OverlordStateStore(runtime_dir)

    def get_policy(self) -> OverlordPolicyResponse:
        return OverlordPolicyResponse(
            auto_remediation_enabled=self.settings.auto_remediation_enabled,
            safe_pause_enabled=self.settings.safe_pause_enabled,
            safe_resume_enabled=self.settings.safe_resume_enabled,
            stale_state_cleanup_enabled=self.settings.stale_state_cleanup_enabled,
            telegram=self._telegram_status(),
        )

    def get_summary(self) -> OverlordSummaryResponse:
        overview = self.overview_service.get_summary()
        runtime = self.gateway_contract_service.get_runtime_surface().runtime
        incidents = self._sort_incidents(
            self._derive_incidents(overview, runtime.github_api_budget, runtime.gemini_api_key_pool)
        )
        recent_actions = self._recent_action_records(limit=10)
        status = self._overall_status(incidents)
        operator_todos = [
            incident.operator_action
            for incident in incidents
            if incident.operator_action and incident.requires_operator
        ]
        headline = self._headline(status, incidents)
        summary = self._summary_text(status, incidents)
        telemetry = {
            "active_incident_count": len(incidents),
            "operator_required_count": sum(1 for incident in incidents if incident.requires_operator),
            "auto_recovering_count": sum(1 for incident in incidents if incident.auto_recovering),
            "paused_agents": sum(1 for agent in overview.agents if agent.is_paused),
            "analysis_pending": overview.analysis.pending,
            "triage_pending": overview.triage.pending,
            "github_budget_exhausted": bool(runtime.github_api_budget.exhausted) if runtime.github_api_budget else False,
            "gemini_pool_available": self._available_gemini_keys(runtime.gemini_api_key_pool),
        }
        return OverlordSummaryResponse(
            status=status,
            headline=headline,
            summary=summary,
            generated_at=datetime.now(timezone.utc),
            incidents=incidents,
            recent_actions=recent_actions,
            operator_todos=operator_todos,
            telemetry=telemetry,
            telegram=self._telegram_status(),
        )

    def evaluate_and_remediate(self) -> OverlordSummaryResponse:
        self._reconcile_stale_runs()
        summary = self.get_summary()
        state = self.state_store.load()
        active_incidents = state.setdefault("active_incidents", {})
        telegram_state = state.setdefault("telegram", {})

        current_keys = {incident.incident_key for incident in summary.incidents}
        now = datetime.now(timezone.utc)

        for incident in summary.incidents:
            previous = active_incidents.get(incident.incident_key)
            if previous is None:
                active_incidents[incident.incident_key] = {
                    "opened_at": now.isoformat(),
                    "severity": incident.severity.value,
                }
                self._emit_incident_event("overlord.incident_opened", incident)
                self._notify_telegram(incident, resolved=False, telegram_state=telegram_state)

        for incident_key in list(active_incidents.keys()):
            if incident_key in current_keys:
                continue
            prior_severity = active_incidents[incident_key].get("severity", EventSeverity.ERROR.value)
            resolved_incident = OverlordIncident(
                incident_key=incident_key,
                title=incident_key.replace("-", " ").replace("_", " ").title(),
                status="resolved",
                system_status="healthy",
                severity=EventSeverity(prior_severity),
                summary="The condition is no longer present.",
                detected_at=None,
                last_observed_at=now,
                why_it_happened="The underlying condition recovered or was remediated.",
                what_overlord_did="Closed the active alert and marked the system recovered.",
                operator_action=None,
            )
            self._emit_incident_event("overlord.incident_resolved", resolved_incident)
            self._notify_telegram(resolved_incident, resolved=True, telegram_state=telegram_state)
            active_incidents.pop(incident_key, None)

        if self.settings.auto_remediation_enabled:
            self._apply_safe_policies(summary)

        self._maybe_send_daily_digest(summary, state)
        self.state_store.save(state)
        return self.get_summary()

    def _apply_safe_policies(self, summary: OverlordSummaryResponse) -> None:
        runtime = self.gateway_contract_service.get_runtime_surface().runtime
        github_exhausted = bool(runtime.github_api_budget.exhausted) if runtime.github_api_budget else False
        gemini_available = self._available_gemini_keys(runtime.gemini_api_key_pool)

        if self.settings.safe_pause_enabled and github_exhausted:
            for agent_name in ("firehose", "backfill"):
                self._pause_agent_if_needed(
                    agent_name,
                    reason="Overlord safe-paused intake because all GitHub tokens are exhausted.",
                    resume_condition="Resume automatically after GitHub budget recovers.",
                    action_summary="Paused intake during GitHub budget exhaustion.",
                )
        if self.settings.safe_resume_enabled and not github_exhausted:
            for agent_name in ("firehose", "backfill"):
                self._resume_agent_if_overlord_managed(
                    agent_name,
                    expected_reason_fragment="GitHub tokens are exhausted",
                    action_summary="Resumed intake after GitHub budget recovered.",
                )

        analyst = next((agent for agent in self.overview_service.get_summary().agents if agent.agent_name == "analyst"), None)
        if analyst and analyst.configured_provider == "gemini-compatible":
            if self.settings.safe_pause_enabled and gemini_available == 0:
                self._pause_agent_if_needed(
                    "analyst",
                    reason="Overlord safe-paused Analyst because all Gemini-compatible keys are unavailable.",
                    resume_condition="Resume automatically after at least one Gemini-compatible key recovers.",
                    action_summary="Paused Analyst during Gemini-compatible key exhaustion.",
                )
            if self.settings.safe_resume_enabled and gemini_available > 0:
                self._resume_agent_if_overlord_managed(
                    "analyst",
                    expected_reason_fragment="Gemini-compatible keys are unavailable",
                    action_summary="Resumed Analyst after Gemini-compatible key capacity recovered.",
                )

    def _pause_agent_if_needed(self, agent_name: str, reason: str, resume_condition: str, action_summary: str) -> None:
        pause_state = self.repository.get_agent_pause_state(agent_name) or self.repository.create_agent_pause_state(agent_name)
        if pause_state.is_paused:
            return
        pause_state.is_paused = True
        pause_state.paused_at = datetime.now(timezone.utc)
        pause_state.pause_reason = reason
        pause_state.resume_condition = resume_condition
        pause_state.triggered_by_event_id = None
        self.repository.update_agent_pause_state(pause_state)
        self.repository.create_system_event(
            event_type="overlord.auto_action",
            agent_name="overlord",
            severity=EventSeverity.WARNING,
            message=f"Overlord safe-paused {agent_name}.",
            context_json=json.dumps({
                "action": "safe_pause",
                "target": agent_name,
                "summary": action_summary,
                "status": "applied",
            }),
            agent_run_id=None,
        )

    def _resume_agent_if_overlord_managed(self, agent_name: str, expected_reason_fragment: str, action_summary: str) -> None:
        pause_state = self.repository.get_agent_pause_state(agent_name)
        if pause_state is None or not pause_state.is_paused:
            return
        reason = pause_state.pause_reason or ""
        if "Overlord safe-paused" not in reason or expected_reason_fragment not in reason:
            return
        pause_state.is_paused = False
        pause_state.resumed_at = datetime.now(timezone.utc)
        pause_state.resumed_by = ResumedBy.AUTO
        self.repository.update_agent_pause_state(pause_state)
        self.repository.create_system_event(
            event_type="overlord.auto_action",
            agent_name="overlord",
            severity=EventSeverity.INFO,
            message=f"Overlord resumed {agent_name} after recovery.",
            context_json=json.dumps({
                "action": "safe_resume",
                "target": agent_name,
                "summary": action_summary,
                "status": "applied",
            }),
            agent_run_id=None,
        )

    def _derive_incidents(
        self,
        overview,
        github_budget: GitHubApiBudgetSnapshot | None,
        gemini_pool: GeminiApiKeyPoolSnapshot | None,
    ) -> list[OverlordIncident]:
        incidents: list[OverlordIncident] = []
        now = datetime.now(timezone.utc)
        latest_runs = {agent.agent_name: agent for agent in overview.agents}

        if github_budget and github_budget.exhausted:
            incidents.append(
                OverlordIncident(
                    incident_key="github-budget-exhausted",
                    title="GitHub budget exhausted",
                    system_status="rate-limited",
                    severity=EventSeverity.CRITICAL,
                    summary="All available GitHub budget appears exhausted, so intake and GitHub-backed analysis may stall.",
                    provider="github",
                    detected_at=self._parse_dt(github_budget.captured_at),
                    last_observed_at=self._parse_dt(github_budget.captured_at),
                    retry_after_seconds=github_budget.retry_after_seconds,
                    requires_operator=False,
                    auto_recovering=True,
                    why_it_happened="The GitHub token pool reported exhaustion on the latest captured budget snapshot.",
                    what_overlord_did="Safely pauses Firehose and Backfill while the budget is exhausted, then resumes them after recovery if auto-remediation is enabled.",
                    operator_action="Add more GitHub capacity or wait for reset only if recovery takes too long.",
                )
            )

        if gemini_pool is not None and self._available_gemini_keys(gemini_pool) == 0 and gemini_pool.keys:
            incidents.append(
                OverlordIncident(
                    incident_key="gemini-pool-exhausted",
                    title="Gemini-compatible key pool exhausted",
                    system_status="rate-limited",
                    severity=EventSeverity.CRITICAL,
                    summary="No Gemini-compatible Analyst key is currently available.",
                    agent_name="analyst",
                    provider="gemini-compatible",
                    detected_at=self._parse_dt(gemini_pool.captured_at),
                    last_observed_at=self._parse_dt(gemini_pool.captured_at),
                    requires_operator=False,
                    auto_recovering=True,
                    why_it_happened="Every key in the Gemini-compatible pool is either cooling down, exhausted, or in error state.",
                    what_overlord_did="Safely pauses Analyst until at least one key becomes available again if auto-remediation is enabled.",
                    operator_action="Check upstream rate limits or add more Gemini-compatible keys if this persists.",
                )
            )

        if overview.analysis.pending >= 25 and latest_runs.get("analyst") and latest_runs["analyst"].is_paused:
            incidents.append(
                OverlordIncident(
                    incident_key="analyst-blocked-backlog",
                    title="Analyst backlog is building while Analyst is paused",
                    system_status="blocked",
                    severity=EventSeverity.ERROR,
                    summary=f"{overview.analysis.pending} accepted repositories are waiting while Analyst is paused.",
                    agent_name="analyst",
                    detected_at=now,
                    last_observed_at=now,
                    requires_operator=True,
                    auto_recovering=False,
                    why_it_happened="Accepted repositories continue to accumulate while Analyst is not currently allowed to process them.",
                    what_overlord_did="Tracked the blocked state and kept it visible on the control surfaces.",
                    operator_action="Review why Analyst is paused and resume it when the provider or policy issue is resolved.",
                )
            )

        if overview.triage.pending >= 50:
            incidents.append(
                OverlordIncident(
                    incident_key="triage-backlog-pressure",
                    title="Triage backlog pressure",
                    system_status="degraded",
                    severity=EventSeverity.WARNING,
                    summary=f"Bouncer has {overview.triage.pending} repositories waiting for triage.",
                    agent_name="bouncer",
                    detected_at=now,
                    last_observed_at=now,
                    requires_operator=False,
                    auto_recovering=True,
                    why_it_happened="Repository intake is currently outrunning downstream triage throughput.",
                    what_overlord_did="Surfaced the pressure so you can distinguish queue growth from outright failure.",
                    operator_action="Pause intake temporarily only if this backlog keeps growing and downstream stages cannot catch up.",
                )
            )

        for agent in overview.agents:
            if agent.status == "failed" and not agent.is_paused:
                _latest_runs = self.repository.list_agent_runs(
                    AgentRunListFilters(agent_name=agent.agent_name, limit=1)
                )
                _latest_err = (_latest_runs[0].error_summary or "") if _latest_runs else ""
                _is_stale_recovery = "stale" in _latest_err.lower() or "drift" in _latest_err.lower()
                if _is_stale_recovery:
                    continue
                incidents.append(
                    OverlordIncident(
                        incident_key=f"failed-agent-{agent.agent_name}",
                        title=f"{agent.display_name} has a failed latest run",
                        system_status="operator-required" if agent.agent_name in {"analyst", "combiner"} else "degraded",
                        severity=EventSeverity.ERROR,
                        summary=f"{agent.display_name} latest run is failed.",
                        agent_name=agent.agent_name,
                        detected_at=now,
                        last_observed_at=now,
                        requires_operator=agent.agent_name in {"analyst", "combiner"},
                        auto_recovering=agent.agent_name in {"firehose", "backfill", "bouncer"},
                        why_it_happened="The latest recorded agent run completed in a failed state.",
                        what_overlord_did="Kept the failure attached to the live state instead of letting it disappear into historical logs.",
                        operator_action="Inspect the latest failure details if repeated retries do not self-heal.",
                    )
                )

        return incidents

    def _overall_status(self, incidents: list[OverlordIncident]) -> str:
        if not incidents:
            return "healthy"
        return incidents[0].system_status

    def _headline(self, status: str, incidents: list[OverlordIncident]) -> str:
        if not incidents:
            return "Overlord sees a healthy pipeline."
        return f"Overlord sees {len(incidents)} active issue{'s' if len(incidents) != 1 else ''}: {status}."

    def _summary_text(self, status: str, incidents: list[OverlordIncident]) -> str:
        if not incidents:
            return "No active incident currently needs intervention. Intake, triage, and analysis surfaces look coherent from Overlord's perspective."
        top = incidents[0]
        return f"Current posture is {status}. Top issue: {top.title.lower()} — {top.summary}"

    def _sort_incidents(self, incidents: list[OverlordIncident]) -> list[OverlordIncident]:
        status_priority = {
            "operator-required": 6,
            "blocked": 5,
            "stale-state-mismatch": 4,
            "rate-limited": 3,
            "auto-recovering": 2,
            "degraded": 1,
            "healthy": 0,
        }
        severity_priority = {
            EventSeverity.CRITICAL: 3,
            EventSeverity.ERROR: 2,
            EventSeverity.WARNING: 1,
            EventSeverity.INFO: 0,
        }
        return sorted(
            incidents,
            key=lambda incident: (
                status_priority[incident.system_status],
                severity_priority[incident.severity],
                incident.requires_operator,
                incident.last_observed_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )

    def _recent_action_records(self, limit: int) -> list[OverlordActionRecord]:
        events = self.repository.list_system_events(
            SystemEventListFilters(agent_name="overlord", event_type="overlord.auto_action", limit=limit)
        )
        records: list[OverlordActionRecord] = []
        for event in events:
            try:
                payload = json.loads(event.context_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            records.append(
                OverlordActionRecord(
                    action=payload.get("action", "notify"),
                    target=payload.get("target", "system"),
                    summary=payload.get("summary", event.message),
                    created_at=event.created_at,
                    status=payload.get("status", "applied"),
                )
            )
        return records

    def _reconcile_stale_runs(self) -> None:
        if not self.settings.stale_state_cleanup_enabled:
            return
        recovered = 0
        for agent_name in ("firehose", "backfill", "bouncer", "analyst"):
            recovered += self.repository.reconcile_stale_running_agent_runs(agent_name)
        if recovered:
            self.repository.create_system_event(
                event_type="overlord.auto_action",
                agent_name="overlord",
                severity=EventSeverity.WARNING,
                message="Overlord cleaned up stale running state.",
                context_json=json.dumps({
                    "action": "stale_state_cleanup",
                    "target": "runtime",
                    "summary": f"Recovered {recovered} stale running agent run(s).",
                    "status": "applied",
                }),
                agent_run_id=None,
            )

    def _emit_incident_event(self, event_type: str, incident: OverlordIncident) -> None:
        self.repository.create_system_event(
            event_type=event_type,
            agent_name="overlord",
            severity=incident.severity,
            message=incident.summary,
            context_json=incident.model_dump_json(),
            agent_run_id=None,
        )

    def _notify_telegram(self, incident: OverlordIncident, resolved: bool, telegram_state: dict) -> None:
        if not self.settings.telegram_enabled:
            return
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return
        severity_rank = {
            EventSeverity.INFO: 0,
            EventSeverity.WARNING: 1,
            EventSeverity.ERROR: 2,
            EventSeverity.CRITICAL: 3,
        }
        if severity_rank[incident.severity] < severity_rank[self.settings.telegram_min_severity] and not resolved:
            return
        state_key = f"{incident.incident_key}:{'resolved' if resolved else 'active'}"
        if telegram_state.get(state_key):
            return
        title = "Recovered" if resolved else incident.title
        prefix = "✅" if resolved else "🚨"
        text = (
            f"{prefix} Overlord\n"
            f"{title}\n\n"
            f"What happened: {incident.summary}\n"
            f"Why: {incident.why_it_happened}\n"
            f"What Overlord did: {incident.what_overlord_did or 'Observed and recorded the incident.'}\n"
            f"What you need to do: {incident.operator_action or 'Nothing right now unless it persists.'}"
        )
        payload = parse.urlencode({"chat_id": self.settings.telegram_chat_id, "text": text}).encode()
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            request.urlopen(request.Request(url, data=payload, method="POST"), timeout=10).read()
            telegram_state[state_key] = datetime.now(timezone.utc).isoformat()
        except (urlerror.URLError, TimeoutError):
            return

    def _maybe_send_daily_digest(self, summary: OverlordSummaryResponse, state: dict) -> None:
        if not self.settings.telegram_enabled or not self.settings.telegram_daily_digest_enabled:
            return
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return
        digest_state = state.setdefault("daily_digest", {})
        today = datetime.now(timezone.utc).date().isoformat()
        if digest_state.get("last_sent_date") == today:
            return
        now = datetime.now(timezone.utc)
        if now.hour < 7:
            return
        text = (
            f"🧾 Overlord daily digest\n\n"
            f"Status: {summary.status}\n"
            f"Active incidents: {len(summary.incidents)}\n"
            f"Operator-required: {len(summary.operator_todos)}\n"
            f"Analysis pending: {summary.telemetry.get('analysis_pending', 0)}\n"
            f"Triage pending: {summary.telemetry.get('triage_pending', 0)}"
        )
        payload = parse.urlencode({"chat_id": self.settings.telegram_chat_id, "text": text}).encode()
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            request.urlopen(request.Request(url, data=payload, method="POST"), timeout=10).read()
            digest_state["last_sent_date"] = today
        except (urlerror.URLError, TimeoutError):
            return

    def _telegram_status(self) -> OverlordTelegramStatus:
        return OverlordTelegramStatus(
            enabled=self.settings.telegram_enabled,
            min_severity=self.settings.telegram_min_severity,
            daily_digest_enabled=self.settings.telegram_daily_digest_enabled,
            configured_chat=bool(self.settings.telegram_chat_id),
            configured_token=bool(self.settings.telegram_bot_token),
        )

    def _available_gemini_keys(self, gemini_pool: GeminiApiKeyPoolSnapshot | None) -> int:
        if gemini_pool is None:
            return 0
        available = 0
        now = datetime.now(timezone.utc)
        for key in gemini_pool.keys:
            cooldown_until = self._parse_dt(key.cooldown_until)
            if key.status.lower() in {"available", "ready", "ok", "healthy", "idle"}:
                available += 1
                continue
            if cooldown_until is not None and cooldown_until <= now:
                available += 1
        return available

    def _parse_dt(self, value: str | datetime | None) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
