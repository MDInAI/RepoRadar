from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core.errors import AppError
from app.repositories.agent_event_repository import AgentEventRepository
from app.schemas.agent_event import AgentManualRunTriggerResponse


_SUPPORTED_AGENT_RUNNERS = {
    "firehose": "run_configured_firehose_job",
    "backfill": "run_configured_backfill_job",
    "bouncer": "run_configured_bouncer_job",
    "analyst": "run_configured_analyst_job",
}


class AgentOperatorService:
    def __init__(
        self,
        repository: AgentEventRepository,
        project_root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.project_root = project_root or Path(__file__).resolve().parents[3]

    def trigger_agent_run(self, agent_name: str) -> AgentManualRunTriggerResponse:
        runner_name = _SUPPORTED_AGENT_RUNNERS.get(agent_name)
        if runner_name is None:
            raise AppError(
                message=f"Agent '{agent_name}' does not support manual run triggers.",
                code="agent_manual_run_unsupported",
                status_code=400,
            )

        pause_state = self.repository.get_agent_pause_state(agent_name)
        if pause_state is not None and pause_state.is_paused:
            raise AppError(
                message=f"Agent '{agent_name}' is paused and must be resumed before it can run.",
                code="agent_paused",
                status_code=409,
            )

        if self.repository.has_running_agent_run(agent_name):
            raise AppError(
                message=f"Agent '{agent_name}' already has a running job.",
                code="agent_run_already_active",
                status_code=409,
            )

        workers_root = self.project_root / "workers"
        python_bin = workers_root / ".venv" / "bin" / "python"
        if not python_bin.exists():
            raise AppError(
                message="Worker Python runtime is not available for manual run triggers.",
                code="worker_python_missing",
                status_code=503,
                details={"expected_path": str(python_bin)},
            )

        script = (
            f"from agentic_workers.main import {runner_name}; "
            f"{runner_name}()"
        )
        import_probe = (
            f"from agentic_workers.main import {runner_name}; "
            "print('import-ok')"
        )

        try:
            probe = subprocess.run(
                [str(python_bin), "-c", import_probe],
                cwd=workers_root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except OSError as exc:
            raise AppError(
                message=f"Failed to verify worker runtime for '{agent_name}'.",
                code="agent_manual_run_probe_failed",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AppError(
                message=f"Worker runtime verification timed out for '{agent_name}'.",
                code="agent_manual_run_probe_timeout",
                status_code=504,
                details={"timeout_seconds": 15, "reason": str(exc)},
            ) from exc

        if probe.returncode != 0:
            stderr = (probe.stderr or "").strip()
            stdout = (probe.stdout or "").strip()
            raise AppError(
                message=f"Worker runtime failed to load '{agent_name}' prerequisites.",
                code="agent_manual_run_probe_import_failed",
                status_code=500,
                details={
                    "returncode": probe.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

        try:
            subprocess.Popen(
                [str(python_bin), "-c", script],
                cwd=workers_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise AppError(
                message=f"Failed to launch manual run for '{agent_name}'.",
                code="agent_manual_run_launch_failed",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc

        return AgentManualRunTriggerResponse(
            agent_name=agent_name,
            triggered_at=datetime.now(timezone.utc),
            message=f"Manual {agent_name} run launched in the worker runtime.",
        )
