from __future__ import annotations

from app.repositories.intake_runtime_repository import (
    BackfillIntakeRuntimeRecord,
    FirehoseIntakeRuntimeRecord,
    IntakeRuntimeRepository,
)
from app.schemas.gateway_contract import (
    GatewayAgentIntakeCheckpoint,
    GatewayAgentIntakeQueueSummary,
    GatewayQueueStateBuckets,
)


class GatewayIntakeRuntimeService:
    def __init__(self, repository: IntakeRuntimeRepository) -> None:
        self.repository = repository

    def build_queue_overrides(self) -> dict[str, GatewayAgentIntakeQueueSummary]:
        firehose_runtime = self.repository.load_firehose_runtime()
        backfill_runtime = self.repository.load_backfill_runtime()
        return {
            "firehose": self._build_firehose_queue(firehose_runtime),
            "backfill": self._build_backfill_queue(backfill_runtime),
        }

    def _build_firehose_queue(
        self,
        runtime: FirehoseIntakeRuntimeRecord,
    ) -> GatewayAgentIntakeQueueSummary:
        return GatewayAgentIntakeQueueSummary(
            pending_items=runtime.counts.pending,
            total_items=runtime.counts.total_items,
            state_counts=GatewayQueueStateBuckets(
                pending=runtime.counts.pending,
                in_progress=runtime.counts.in_progress,
                completed=runtime.counts.completed,
                failed=runtime.counts.failed,
            ),
            checkpoint=GatewayAgentIntakeCheckpoint(
                kind="firehose",
                next_page=runtime.next_page,
                last_checkpointed_at=runtime.last_checkpointed_at,
                mirror_snapshot_generated_at=runtime.mirror_snapshot_generated_at,
                active_mode=runtime.active_mode,
                resume_required=runtime.resume_required,
                new_anchor_date=runtime.new_anchor_date,
                trending_anchor_date=runtime.trending_anchor_date,
                run_started_at=runtime.run_started_at,
            ),
            notes=self._build_queue_notes(
                "firehose",
                mirror_snapshot_generated_at=runtime.mirror_snapshot_generated_at,
                snapshot_issue_note=runtime.snapshot_issue_note,
            ),
        )

    def _build_backfill_queue(
        self,
        runtime: BackfillIntakeRuntimeRecord,
    ) -> GatewayAgentIntakeQueueSummary:
        return GatewayAgentIntakeQueueSummary(
            pending_items=runtime.counts.pending,
            total_items=runtime.counts.total_items,
            state_counts=GatewayQueueStateBuckets(
                pending=runtime.counts.pending,
                in_progress=runtime.counts.in_progress,
                completed=runtime.counts.completed,
                failed=runtime.counts.failed,
            ),
            checkpoint=GatewayAgentIntakeCheckpoint(
                kind="backfill",
                next_page=runtime.next_page,
                last_checkpointed_at=runtime.last_checkpointed_at,
                mirror_snapshot_generated_at=runtime.mirror_snapshot_generated_at,
                window_start_date=runtime.window_start_date,
                created_before_boundary=runtime.created_before_boundary,
                created_before_cursor=runtime.created_before_cursor,
                exhausted=runtime.exhausted,
            ),
            notes=self._build_queue_notes(
                "backfill",
                mirror_snapshot_generated_at=runtime.mirror_snapshot_generated_at,
                snapshot_issue_note=runtime.snapshot_issue_note,
            ),
        )

    @staticmethod
    def _build_queue_notes(
        intake_key: str,
        *,
        mirror_snapshot_generated_at: object | None,
        snapshot_issue_note: str | None,
    ) -> list[str]:
        notes = [
            "Queue counts and checkpoint metadata come from Agentic-Workflow persistence.",
            "Gateway-owned routing and session fields remain backend-mediated on this surface.",
        ]
        if mirror_snapshot_generated_at is not None:
            notes.append(
                f"The runtime/{intake_key}/progress.json snapshot is available as a mirror artifact."
            )
        if snapshot_issue_note is not None:
            notes.append(snapshot_issue_note)
        return notes
