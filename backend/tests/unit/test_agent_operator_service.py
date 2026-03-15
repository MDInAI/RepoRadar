from __future__ import annotations

from pathlib import Path

import pytest
import subprocess

from app.core.errors import AppError
from app.models import AgentPauseState, AgentRun, AgentRunStatus
from app.repositories.agent_event_repository import AgentEventRepository
from app.services.agent_operator_service import AgentOperatorService


def test_trigger_agent_run_launches_worker_subprocess(
    session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_root = tmp_path / "workers"
    python_bin = workers_root / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(args, cwd, capture_output, text, timeout, check):
        captured["probe_args"] = args
        captured["probe_cwd"] = cwd
        captured["probe_timeout"] = timeout
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="import-ok\n", stderr="")

    def fake_popen(args, cwd, stdout, stderr, start_new_session):
        captured["args"] = args
        captured["cwd"] = cwd
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session

        class _Proc:
            pid = 12345

        return _Proc()

    monkeypatch.setattr("app.services.agent_operator_service.subprocess.run", fake_run)
    monkeypatch.setattr("app.services.agent_operator_service.subprocess.Popen", fake_popen)

    service = AgentOperatorService(AgentEventRepository(session), project_root=tmp_path)
    response = service.trigger_agent_run("firehose")

    assert response.accepted is True
    assert response.agent_name == "firehose"
    assert response.trigger_mode == "background-subprocess"
    assert captured["cwd"] == workers_root
    assert captured["start_new_session"] is True
    assert captured["probe_cwd"] == workers_root
    assert captured["probe_timeout"] == 15
    assert captured["args"] == [
        str(python_bin),
        "-c",
        "from agentic_workers.main import run_configured_firehose_job; run_configured_firehose_job()",
    ]


def test_trigger_agent_run_rejects_paused_agent(session, tmp_path: Path) -> None:
    session.add(
        AgentPauseState(
            agent_name="firehose",
            is_paused=True,
            pause_reason="Manual pause",
        )
    )
    session.commit()

    service = AgentOperatorService(AgentEventRepository(session), project_root=tmp_path)

    with pytest.raises(AppError, match="must be resumed"):
        service.trigger_agent_run("firehose")


def test_trigger_agent_run_rejects_already_running_agent(session, tmp_path: Path) -> None:
    session.add(AgentRun(agent_name="backfill", status=AgentRunStatus.RUNNING))
    session.commit()

    service = AgentOperatorService(AgentEventRepository(session), project_root=tmp_path)

    with pytest.raises(AppError, match="already has a running job"):
        service.trigger_agent_run("backfill")


def test_trigger_agent_run_rejects_worker_import_failures(
    session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workers_root = tmp_path / "workers"
    python_bin = workers_root / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("", encoding="utf-8")

    def fake_run(args, cwd, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="IndentationError: unexpected indent",
        )

    monkeypatch.setattr("app.services.agent_operator_service.subprocess.run", fake_run)

    service = AgentOperatorService(AgentEventRepository(session), project_root=tmp_path)

    with pytest.raises(AppError, match="failed to load 'firehose' prerequisites"):
        service.trigger_agent_run("firehose")
