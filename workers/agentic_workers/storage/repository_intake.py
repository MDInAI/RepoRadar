from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

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


class IntakePersistenceError(RuntimeError):
    def __init__(
        self,
        *,
        github_repository_id: int,
        operation: str,
        message: str,
    ) -> None:
        self.github_repository_id = github_repository_id
        self.operation = operation
        super().__init__(
            f"Repository intake {operation} failed for github_repository_id="
            f"{github_repository_id}: {message}"
        )


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

    now = datetime.now(timezone.utc)
    inserted_count = 0
    skipped_count = 0

    for repository in repositories:
        try:
            inserted = _insert_repository(
                session,
                repository,
                discovery_source=discovery_source,
                firehose_mode=firehose_mode,
                now=now,
            )
            if inserted:
                inserted_count += 1
                continue

            _refresh_repository_metadata(session, repository)
            skipped_count += 1
        except (SQLAlchemyError, ValueError) as exc:
            rollback = getattr(session, "rollback", None)
            if callable(rollback):
                rollback()
            raise IntakePersistenceError(
                github_repository_id=repository.github_repository_id,
                operation="upsert",
                message=str(exc),
            ) from exc

    if commit:
        session.commit()
    return IntakePersistenceResult(inserted_count=inserted_count, skipped_count=skipped_count)


def _insert_repository(
    session: Session,
    repository: DiscoveredRepository,
    *,
    discovery_source: RepositoryDiscoverySource,
    firehose_mode: FirehoseMode | None,
    now: datetime,
) -> bool:
    insert_result = session.execute(
        sqlite_insert(RepositoryIntake)
        .values(
            github_repository_id=repository.github_repository_id,
            source_provider="github",
            owner_login=repository.owner_login,
            repository_name=repository.repository_name,
            full_name=repository.full_name,
            repository_description=repository.description,
            stargazers_count=repository.stargazers_count,
            forks_count=repository.forks_count,
            github_created_at=repository.created_at,
            pushed_at=repository.pushed_at,
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
        .on_conflict_do_nothing(index_elements=[RepositoryIntake.github_repository_id])
    )
    return bool(insert_result.rowcount)


def _refresh_repository_metadata(
    session: Session,
    repository: DiscoveredRepository,
) -> None:
    session.execute(
        update(RepositoryIntake)
        .where(RepositoryIntake.github_repository_id == repository.github_repository_id)
        .values(
            owner_login=repository.owner_login,
            repository_name=repository.repository_name,
            full_name=repository.full_name,
            repository_description=repository.description,
            stargazers_count=repository.stargazers_count,
            forks_count=repository.forks_count,
            github_created_at=repository.created_at,
            pushed_at=repository.pushed_at,
        )
    )
