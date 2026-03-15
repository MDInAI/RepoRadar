from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppError
from app.schemas.agent_config import AgentConfigUpdateRequest
from app.services.agent_config_service import AgentConfigService


def test_get_agent_config_reads_worker_override_values(tmp_path: Path) -> None:
    backend_dir = tmp_path / "backend"
    workers_dir = tmp_path / "workers"
    backend_dir.mkdir()
    workers_dir.mkdir()
    (backend_dir / ".env").write_text("FIREHOSE_INTERVAL_SECONDS=3600\n", encoding="utf-8")
    (workers_dir / ".env").write_text("FIREHOSE_INTERVAL_SECONDS=1800\n", encoding="utf-8")

    service = AgentConfigService(project_root=tmp_path)
    response = service.get_agent_config("firehose")

    interval_field = next(field for field in response.fields if field.key == "FIREHOSE_INTERVAL_SECONDS")
    assert interval_field.value == "1800"


def test_update_agent_config_persists_to_backend_and_workers_env(tmp_path: Path) -> None:
    backend_dir = tmp_path / "backend"
    workers_dir = tmp_path / "workers"
    backend_dir.mkdir()
    workers_dir.mkdir()
    (backend_dir / ".env").write_text("FIREHOSE_INTERVAL_SECONDS=3600\n", encoding="utf-8")
    (workers_dir / ".env").write_text("FIREHOSE_INTERVAL_SECONDS=3600\n", encoding="utf-8")

    service = AgentConfigService(project_root=tmp_path)
    response = service.update_agent_config(
        "firehose",
        AgentConfigUpdateRequest(
            values={
                "FIREHOSE_INTERVAL_SECONDS": "900",
                "FIREHOSE_PER_PAGE": "50",
                "FIREHOSE_PAGES": "4",
                "GITHUB_REQUESTS_PER_MINUTE": "80",
                "INTAKE_PACING_SECONDS": "15",
            }
        ),
    )

    assert "Manual runs use the new values immediately" in response.message
    assert "FIREHOSE_INTERVAL_SECONDS=900" in (backend_dir / ".env").read_text(encoding="utf-8")
    worker_text = (workers_dir / ".env").read_text(encoding="utf-8")
    assert "FIREHOSE_INTERVAL_SECONDS=900" in worker_text
    assert "FIREHOSE_PER_PAGE=50" in worker_text
    assert "FIREHOSE_PAGES=4" in worker_text


def test_update_agent_config_rejects_invalid_backfill_date(tmp_path: Path) -> None:
    service = AgentConfigService(project_root=tmp_path)

    with pytest.raises(AppError, match="YYYY-MM-DD"):
        service.update_agent_config(
            "backfill",
            AgentConfigUpdateRequest(values={"BACKFILL_MIN_CREATED_DATE": "03/15/2026"}),
        )


def test_update_agent_config_normalizes_csv_rules(tmp_path: Path) -> None:
    service = AgentConfigService(project_root=tmp_path)
    response = service.update_agent_config(
        "bouncer",
        AgentConfigUpdateRequest(
            values={
                "BOUNCER_INCLUDE_RULES": " workflow, analytics , devtools ",
                "BOUNCER_EXCLUDE_RULES": "",
                "INTAKE_PACING_SECONDS": "20",
            }
        ),
    )

    include_field = next(field for field in response.fields if field.key == "BOUNCER_INCLUDE_RULES")
    assert include_field.value == "workflow, analytics, devtools"
