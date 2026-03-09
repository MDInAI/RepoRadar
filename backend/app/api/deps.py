from collections.abc import Generator

from fastapi import Depends
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.repositories.intake_runtime_repository import IntakeRuntimeRepository
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.repositories.repository_triage_repository import RepositoryTriageRepository
from app.services.intake_runtime_service import GatewayIntakeRuntimeService
from app.services.openclaw.contract_service import GatewayContractService
from app.services.repository_exploration_service import RepositoryExplorationService
from app.services.repository_triage_service import RepositoryTriageService
from app.services.settings_service import SettingsService


def get_db_session() -> Generator[Session, None, None]:
    yield from get_session()


def get_gateway_contract_service(
    session: Session = Depends(get_db_session),
) -> GatewayContractService:
    intake_runtime_service = GatewayIntakeRuntimeService(
        IntakeRuntimeRepository(
            session,
            runtime_dir=settings.AGENTIC_RUNTIME_DIR,
        )
    )
    return GatewayContractService(intake_runtime_service=intake_runtime_service)


def get_repository_triage_service(
    session: Session = Depends(get_db_session),
) -> RepositoryTriageService:
    return RepositoryTriageService(RepositoryTriageRepository(session))


def get_repository_exploration_service(
    session: Session = Depends(get_db_session),
) -> RepositoryExplorationService:
    return RepositoryExplorationService(RepositoryExplorationRepository(session))


def get_settings_service() -> SettingsService:
    return SettingsService()
