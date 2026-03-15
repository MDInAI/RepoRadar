from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sqlmodel import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import engine  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.repositories.repository_artifact_payload_repository import (  # noqa: E402
    RepositoryArtifactPayloadRepository,
)
from app.services.artifact_payload_backfill_service import (  # noqa: E402
    ArtifactPayloadBackfillService,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill repository artifact payloads from legacy runtime files."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of artifact metadata rows to scan.",
    )
    args = parser.parse_args()

    with Session(engine) as session:
        repository = RepositoryArtifactPayloadRepository(
            session,
            runtime_dir=settings.AGENTIC_RUNTIME_DIR,
        )
        service = ArtifactPayloadBackfillService(session, repository)
        result = service.backfill(limit=args.limit)

    print(
        (
            "artifact payload backfill complete: "
            f"scanned={result.scanned} "
            f"imported={result.imported} "
            f"skipped_existing={result.skipped_existing} "
            f"missing_legacy_file={result.missing_legacy_file}"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
