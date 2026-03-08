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
    commit: bool = True,
) -> IntakePersistenceResult:
    return persist_repository_batch(
        session,
        repositories,
        discovery_source=RepositoryDiscoverySource.FIREHOSE,
        firehose_mode=mode,
        commit=commit,
    )


def persist_backfill_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    commit: bool = True,
) -> IntakePersistenceResult:
    return persist_repository_batch(
        session,
        repositories,
        discovery_source=RepositoryDiscoverySource.BACKFILL,
        firehose_mode=None,
        commit=commit,
    )


def persist_repository_batch(
    session: Session,
    repositories: list[DiscoveredRepository],
    *,
    discovery_source: RepositoryDiscoverySource,
    firehose_mode: FirehoseMode | None,
    commit: bool = True,
) -> IntakePersistenceResult:
    if not repositories:
        return IntakePersistenceResult(inserted_count=0, skipped_count=0)
    if discovery_source is RepositoryDiscoverySource.FIREHOSE and firehose_mode is None:
        raise ValueError("firehose_mode is required for firehose batches")
    if discovery_source is not RepositoryDiscoverySource.FIREHOSE and firehose_mode is not None:
        raise ValueError("firehose_mode must be omitted for non-firehose batches")

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
                discovery_source=discovery_source,
                firehose_discovery_mode=(
                    RepositoryFirehoseMode(firehose_mode.value)
                    if firehose_mode is not None
                    else None
                ),
                queue_status=RepositoryQueueStatus.PENDING,
                discovered_at=now,
                queue_created_at=now,
                status_updated_at=now,
            )
        )
        existing_ids.add(repository.github_repository_id)
        inserted_count += 1

    if commit:
        session.commit()
    return IntakePersistenceResult(inserted_count=inserted_count, skipped_count=skipped_count)
