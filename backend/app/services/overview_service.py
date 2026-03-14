from __future__ import annotations

from sqlalchemy import func, select
from sqlmodel import Session

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
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.schemas.overview import (
    AgentHealthMetrics,
    AnalysisMetrics,
    BacklogMetrics,
    FailureMetrics,
    IngestionMetrics,
    OverviewSummaryResponse,
    TriageMetrics,
)


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
        )

    def _get_ingestion_metrics(self) -> IngestionMetrics:
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
        return IngestionMetrics(
            total_repositories=total or 0,
            pending_intake=pending or 0,
            firehose_discovered=firehose or 0,
            backfill_discovered=backfill or 0,
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
        from sqlalchemy import distinct, desc
        from sqlalchemy.orm import aliased

        subq = (
            select(
                AgentRun.agent_name,
                AgentRun.id,
                AgentRun.started_at,
                AgentRun.status,
                func.row_number()
                .over(
                    partition_by=AgentRun.agent_name,
                    order_by=(desc(AgentRun.started_at), desc(AgentRun.id)),
                )
                .label("rn"),
            )
            .subquery()
        )

        latest_runs_query = select(
            subq.c.agent_name,
            subq.c.id,
            subq.c.started_at,
            subq.c.status,
        ).where(subq.c.rn == 1)

        latest_runs = {
            row.agent_name: row
            for row in self.session.execute(latest_runs_query)
        }

        all_pause_states = list(self.session.execute(select(AgentPauseState)).scalars().all())
        pause_states = {state.agent_name: state for state in all_pause_states}

        return [
            AgentHealthMetrics(
                agent_name=name,
                status=latest_runs[name].status if name in latest_runs else None,
                is_paused=pause_states.get(name, AgentPauseState(agent_name=name)).is_paused,
                last_run_at=(
                    latest_runs[name].started_at.isoformat() if name in latest_runs else None
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
