from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sqlmodel import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.services.runtime_history_archive_service import (  # noqa: E402
    RuntimeHistoryArchiveService,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive and prune old operational history from system_events and agent_runs."
    )
    parser.add_argument(
        "--event-retention-days",
        type=int,
        default=settings.OPERATIONAL_EVENT_RETENTION_DAYS,
        help="Keep system_events newer than this many days in the live database.",
    )
    parser.add_argument(
        "--run-retention-days",
        type=int,
        default=settings.OPERATIONAL_RUN_RETENTION_DAYS,
        help="Keep completed/failed/skipped agent_runs newer than this many days in the live database.",
    )
    parser.add_argument(
        "--event-limit",
        type=int,
        default=None,
        help="Optional maximum number of system_events to archive in this execution.",
    )
    parser.add_argument(
        "--run-limit",
        type=int,
        default=None,
        help="Optional maximum number of agent_runs to archive in this execution.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        service = RuntimeHistoryArchiveService(session, settings.AGENTIC_RUNTIME_DIR)
        result = service.archive_operational_history(
            event_retention_days=args.event_retention_days,
            run_retention_days=args.run_retention_days,
            event_limit=args.event_limit,
            run_limit=args.run_limit,
        )

    print(
        "operational history archive complete: "
        f"system_events_exported={result.system_events.exported_count} "
        f"system_events_deleted={result.system_events.deleted_count} "
        f"system_events_archive={result.system_events.archive_path} "
        f"agent_runs_exported={result.agent_runs.exported_count} "
        f"agent_runs_deleted={result.agent_runs.deleted_count} "
        f"agent_runs_archive={result.agent_runs.archive_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
