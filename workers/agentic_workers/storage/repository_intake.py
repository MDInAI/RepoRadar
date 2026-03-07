from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from agentic_workers.providers.github_provider import DiscoveredRepository, FirehoseMode
from agentic_workers.storage.backend_models import (
    RepositoryDiscoverySource,
    RepositoryFirehoseMode,
    RepositoryIntake,
    RepositoryQueueStatus,
)


@dataclass(frozen=True, slots=True)
class IntakePersistenceResult:
    inserted_count: int
    skipped_count: int


def persist_firehose_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    mode: FirehoseMode,
) -> IntakePersistenceResult:
    if not repositories:
        return IntakePersistenceResult(inserted_count=0, skipped_count=0)

    repository_ids = [repository.github_repository_id for repository in repositories]
    existing_ids = set(
        session.exec(
            select(RepositoryIntake.github_repository_id).where(
                RepositoryIntake.github_repository_id.in_(repository_ids)
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    inserted_count = 0
    skipped_count = 0

    for repository in repositories:
        if repository.github_repository_id in existing_ids:
            skipped_count += 1
            continue

        session.add(
            RepositoryIntake(
                github_repository_id=repository.github_repository_id,
                source_provider="github",
                owner_login=repository.owner_login,
                repository_name=repository.repository_name,
                full_name=repository.full_name,
                discovery_source=RepositoryDiscoverySource.FIREHOSE,
                firehose_discovery_mode=RepositoryFirehoseMode(mode.value),
                queue_status=RepositoryQueueStatus.PENDING,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            )
        )
        existing_ids.add(repository.github_repository_id)
        inserted_count += 1

    session.commit()
    return IntakePersistenceResult(inserted_count=inserted_count, skipped_count=skipped_count)
