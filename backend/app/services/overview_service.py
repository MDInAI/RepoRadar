from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlmodel import Session

from app.core.config import settings
from app.models import (
    AGENT_NAMES,
    AgentPauseState,
    AgentRun,
    FailureClassification,
    FailureSeverity,
    RepositoryAnalysisStatus,
    RepositoryDiscoverySource,
    RepositoryIntake,
    RepositoryQueueStatus,
    RepositoryTriageStatus,
    SystemEvent,
)
from app.repositories.agent_event_repository import AgentEventRepository
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.schemas.overview import (
    AgentHealthMetrics,
    AnalysisMetrics,
    BacklogMetrics,
    FailureMetrics,
    IngestionMetrics,
    OverviewSummaryResponse,
    TokenUsageMetrics,
    TriageMetrics,
)
from app.services.agent_metadata import get_agent_metadata
from app.services.agent_runtime_progress_service import AgentRuntimeProgressService


class OverviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo_repository = RepositoryExplorationRepository(session)

    def get_summary(self) -> OverviewSummaryResponse:
        return OverviewSummaryResponse(
            ingestion=self._get_ingestion_metrics(),
            triage=self._get_triage_metrics(),
            analysis=self._get_analysis_metrics(),
            backlog=self._get_backlog_metrics(),
            agents=self._get_agent_health_metrics(),
            failures=self._get_failure_metrics(),
            token_usage=self._get_token_usage_metrics(),
        )

    def _get_ingestion_metrics(self) -> IngestionMetrics:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        total = self.session.scalar(select(func.count(RepositoryIntake.github_repository_id)))
        pending = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.queue_status == RepositoryQueueStatus.PENDING
            )
        )
        firehose = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.discovery_source == RepositoryDiscoverySource.FIREHOSE
            )
        )
        backfill = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.discovery_source == RepositoryDiscoverySource.BACKFILL
            )
        )
        discovered_last_24h = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.discovered_at >= since
            )
        )
        firehose_last_24h = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.discovery_source == RepositoryDiscoverySource.FIREHOSE,
                RepositoryIntake.discovered_at >= since,
            )
        )
        backfill_last_24h = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.discovery_source == RepositoryDiscoverySource.BACKFILL,
                RepositoryIntake.discovered_at >= since,
            )
        )
        return IngestionMetrics(
            total_repositories=total or 0,
            pending_intake=pending or 0,
            firehose_discovered=firehose or 0,
            backfill_discovered=backfill or 0,
            discovered_last_24h=discovered_last_24h or 0,
            firehose_discovered_last_24h=firehose_last_24h or 0,
            backfill_discovered_last_24h=backfill_last_24h or 0,
        )

    def _get_triage_metrics(self) -> TriageMetrics:
        pending = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.triage_status == RepositoryTriageStatus.PENDING
            )
        )
        accepted = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.triage_status == RepositoryTriageStatus.ACCEPTED
            )
        )
        rejected = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.triage_status == RepositoryTriageStatus.REJECTED
            )
        )
        return TriageMetrics(pending=pending or 0, accepted=accepted or 0, rejected=rejected or 0)

    def _get_analysis_metrics(self) -> AnalysisMetrics:
        pending = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.analysis_status == RepositoryAnalysisStatus.PENDING
            )
        )
        in_progress = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.analysis_status == RepositoryAnalysisStatus.IN_PROGRESS
            )
        )
        completed = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.analysis_status == RepositoryAnalysisStatus.COMPLETED
            )
        )
        failed = self.session.scalar(
            select(func.count(RepositoryIntake.github_repository_id)).where(
                RepositoryIntake.analysis_status == RepositoryAnalysisStatus.FAILED
            )
        )
        return AnalysisMetrics(
            pending=pending or 0, in_progress=in_progress or 0, completed=completed or 0, failed=failed or 0
        )

    def _get_backlog_metrics(self) -> BacklogMetrics:
        summary = self.repo_repository.get_repository_backlog_summary()
        return BacklogMetrics(
            queue_pending=summary.queue.get("pending", 0),
            queue_in_progress=summary.queue.get("in_progress", 0),
            queue_completed=summary.queue.get("completed", 0),
            queue_failed=summary.queue.get("failed", 0),
            triage_pending=summary.triage.get("pending", 0),
            triage_accepted=summary.triage.get("accepted", 0),
            triage_rejected=summary.triage.get("rejected", 0),
            analysis_pending=summary.analysis.get("pending", 0),
            analysis_in_progress=summary.analysis.get("in_progress", 0),
            analysis_completed=summary.analysis.get("completed", 0),
            analysis_failed=summary.analysis.get("failed", 0),
        )

    def _get_agent_health_metrics(self) -> list[AgentHealthMetrics]:
        latest_runs = {
            row.agent_name: row
            for row in AgentEventRepository(self.session).get_latest_run_per_agent()
        }

        all_pause_states = list(self.session.execute(select(AgentPauseState)).scalars().all())
        pause_states = {state.agent_name: state for state in all_pause_states}

        usage_by_name = self._get_agent_usage_24h()
        runtime_progress_service = AgentRuntimeProgressService(
            self.session,
            runtime_dir=getattr(settings, "AGENTIC_RUNTIME_DIR", None),
        )

        return [
            AgentHealthMetrics(
                agent_name=name,
                display_name=(metadata := get_agent_metadata(name)).display_name,
                role_label=metadata.role_label,
                description=metadata.description,
                implementation_status=metadata.implementation_status,
                runtime_kind=metadata.runtime_kind,
                uses_github_token=metadata.uses_github_token,
                uses_model=metadata.uses_model,
                configured_provider=metadata.configured_provider,
                configured_model=metadata.configured_model,
                notes=list(metadata.notes),
                status=latest_runs[name].status if name in latest_runs else None,
                is_paused=pause_states.get(name, AgentPauseState(agent_name=name)).is_paused,
                last_run_at=(
                    latest_runs[name].started_at.isoformat() if name in latest_runs else None
                ),
                token_usage_24h=usage_by_name.get(name, {}).get("total_tokens", 0),
                input_tokens_24h=usage_by_name.get(name, {}).get("input_tokens", 0),
                output_tokens_24h=usage_by_name.get(name, {}).get("output_tokens", 0),
                runtime_progress=runtime_progress_service.build_for_agent(
                    name,
                    latest_runs.get(name),
                ),
            )
            for name in AGENT_NAMES
        ]

    def _get_failure_metrics(self) -> FailureMetrics:
        total = self.session.scalar(
            select(func.count(SystemEvent.id)).where(SystemEvent.failure_classification.isnot(None))
        )
        critical = self.session.scalar(
            select(func.count(SystemEvent.id)).where(
                SystemEvent.failure_severity == FailureSeverity.CRITICAL
            )
        )
        rate_limited = self.session.scalar(
            select(func.count(SystemEvent.id)).where(
                SystemEvent.failure_classification == FailureClassification.RATE_LIMITED
            )
        )
        blocking = self.session.scalar(
            select(func.count(SystemEvent.id)).where(
                SystemEvent.failure_classification == FailureClassification.BLOCKING
            )
        )
        return FailureMetrics(
            total_failures=total or 0,
            critical_failures=critical or 0,
            rate_limited_failures=rate_limited or 0,
            blocking_failures=blocking or 0,
        )

    def _get_agent_usage_24h(self) -> dict[str, dict[str, int]]:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = self.session.exec(
            select(
                AgentRun.agent_name,
                func.coalesce(func.sum(AgentRun.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(AgentRun.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(AgentRun.total_tokens), 0).label("total_tokens"),
            )
            .where(AgentRun.started_at >= since)
            .group_by(AgentRun.agent_name)
        ).all()

        usage_by_name: dict[str, dict[str, int]] = {}
        for row in rows:
            usage_by_name[row.agent_name] = {
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
            }
        return usage_by_name

    def _get_token_usage_metrics(self) -> TokenUsageMetrics:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        totals = self.session.exec(
            select(
                func.coalesce(func.sum(AgentRun.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(AgentRun.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(AgentRun.total_tokens), 0).label("total_tokens"),
                func.count(AgentRun.total_tokens).label("llm_runs"),
            ).where(AgentRun.started_at >= since)
        ).one()

        top_consumer = self.session.exec(
            select(
                AgentRun.agent_name,
                func.coalesce(func.sum(AgentRun.total_tokens), 0).label("total_tokens"),
            )
            .where(AgentRun.started_at >= since)
            .group_by(AgentRun.agent_name)
            .order_by(func.coalesce(func.sum(AgentRun.total_tokens), 0).desc(), AgentRun.agent_name.asc())
            .limit(1)
        ).first()

        top_agent_name = None
        top_agent_tokens = 0
        if top_consumer is not None and int(top_consumer.total_tokens or 0) > 0:
            top_agent_name = str(top_consumer.agent_name)
            top_agent_tokens = int(top_consumer.total_tokens or 0)

        return TokenUsageMetrics(
            total_tokens_24h=int(totals.total_tokens or 0),
            input_tokens_24h=int(totals.input_tokens or 0),
            output_tokens_24h=int(totals.output_tokens or 0),
            llm_runs_24h=int(totals.llm_runs or 0),
            top_consumer_agent_name=top_agent_name,
            top_consumer_tokens_24h=top_agent_tokens,
        )
