from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import logging
from pathlib import Path

from sqlmodel import Session, select

from agentic_workers.core.pause_manager import is_agent_paused
from agentic_workers.providers.combiner_provider import (
    AnthropicCombinerProvider,
    HeuristicCombinerProvider,
    RetryableCombinerProvider,
)
from agentic_workers.storage.backend_models import (
    RepositoryIntake,
    SynthesisRun,
    SynthesisRunStatus,
)
from agentic_workers.utils.synthesis_parser import parse_synthesis_output

logger = logging.getLogger(__name__)


class CombinerRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED_PAUSED = "skipped_paused"


@dataclass(frozen=True, slots=True)
class CombinerRunResult:
    status: CombinerRunStatus
    run_id: int | None
    error_message: str | None = None


def run_combiner_job(
    *,
    session: Session,
    runtime_dir: Path | None,
) -> CombinerRunResult:
    # Check if agent is paused
    if is_agent_paused(session, "combiner"):
        logger.info("Combiner is paused, skipping run")
        return CombinerRunResult(
            status=CombinerRunStatus.SKIPPED_PAUSED,
            run_id=None,
        )

    # Find pending synthesis runs
    stmt = select(SynthesisRun).where(
        SynthesisRun.status == SynthesisRunStatus.PENDING,
        SynthesisRun.run_type == "combiner",
    ).limit(1)

    run = session.exec(stmt).first()
    if not run:
        logger.debug("No pending combiner runs found")
        return CombinerRunResult(
            status=CombinerRunStatus.SUCCESS,
            run_id=None,
        )

    try:
        # Mark as running
        run.status = SynthesisRunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()

        # Load previous memory if obsession context exists
        previous_insights = None
        if run.obsession_context_id:
            import json
            from agentic_workers.storage.memory_repository import MemoryRepository
            memory_repo = MemoryRepository(session)
            mem = memory_repo.read_segment(
                obsession_context_id=run.obsession_context_id,
                segment_key="insights"
            )
            if mem:
                # Deserialize JSON list back to string for provider
                try:
                    insights_list = json.loads(mem.content)
                    previous_insights = "\n".join(insights_list) if isinstance(insights_list, list) else mem.content
                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to decode memory segment for context {run.obsession_context_id}, "
                        f"segment_key='insights': {e}. Using raw content as fallback."
                    )
                    previous_insights = mem.content
                logger.info(f"Loaded previous insights for context {run.obsession_context_id}")

        # Load repository READMEs
        readme_contents = []
        for repo_id in run.input_repository_ids:
            repo = session.get(RepositoryIntake, repo_id)
            if not repo:
                raise ValueError(f"Repository {repo_id} not found")

            # Load README artifact from data/readmes/{github_repository_id}.md
            if runtime_dir:
                readme_path = runtime_dir / "data" / "readmes" / f"{repo.github_repository_id}.md"
                if readme_path.exists():
                    readme_contents.append({
                        "full_name": repo.full_name,
                        "content": readme_path.read_text(encoding="utf-8"),
                    })

        if not readme_contents:
            raise ValueError("No README artifacts found for input repositories")

        # Generate synthesis output with retry logic
        # Use LLM provider if API key available, fallback to heuristic
        import os
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = RetryableCombinerProvider(AnthropicCombinerProvider())
        else:
            provider = RetryableCombinerProvider(HeuristicCombinerProvider())
        output = provider.synthesize(readme_contents, previous_insights)

        # Parse structured output
        try:
            parsed = parse_synthesis_output(output)
            run.title = parsed.get("title")
            run.summary = parsed.get("summary")
            run.key_insights = parsed.get("key_insights")
        except Exception as parse_exc:
            logger.warning(f"Failed to parse synthesis output: {parse_exc}")
            # Continue without structured data

        # Mark as completed and persist memory atomically
        run.status = SynthesisRunStatus.COMPLETED
        run.output_text = output
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)

        # Persist memory if obsession context exists
        if run.obsession_context_id and run.key_insights:
            try:
                import json
                from agentic_workers.storage.memory_repository import MemoryRepository
                memory_repo = MemoryRepository(session)

                # Serialize list[str] to JSON
                insights_json = json.dumps(run.key_insights)
                memory_repo.write_segment(
                    obsession_context_id=run.obsession_context_id,
                    segment_key="insights",
                    content=insights_json,
                    content_type="json"
                )

                # Also persist title and summary if available
                if run.title:
                    memory_repo.write_segment(
                        obsession_context_id=run.obsession_context_id,
                        segment_key="title",
                        content=run.title,
                        content_type="markdown"
                    )
                if run.summary:
                    memory_repo.write_segment(
                        obsession_context_id=run.obsession_context_id,
                        segment_key="summary",
                        content=run.summary,
                        content_type="markdown"
                    )

                logger.info(f"Persisted memory segments to context {run.obsession_context_id}")
            except Exception as mem_exc:
                logger.error(f"Failed to persist memory for context {run.obsession_context_id}: {mem_exc}")
                session.rollback()
                raise

        session.commit()

        logger.info(f"Combiner run {run.id} completed successfully")
        return CombinerRunResult(
            status=CombinerRunStatus.SUCCESS,
            run_id=run.id,
        )

    except Exception as exc:
        logger.exception(f"Combiner run {run.id} failed")
        run.status = SynthesisRunStatus.FAILED
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()

        return CombinerRunResult(
            status=CombinerRunStatus.FAILED,
            run_id=run.id,
            error_message=str(exc),
        )
