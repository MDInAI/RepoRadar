from collections.abc import Generator
from pathlib import Path

from fastapi import Depends, Request
from sqlmodel import Session

from app.core.config import Settings, settings
from app.core.database import get_session
from app.core.event_broadcaster import EventBroadcaster
from app.repositories.agent_event_repository import AgentEventRepository
from app.repositories.idea_family_repository import IdeaFamilyRepository
from app.repositories.intake_runtime_repository import IntakeRuntimeRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.obsession_repository import ObsessionRepository
from app.repositories.repository_curation_repository import RepositoryCurationRepository
from app.repositories.repository_artifact_payload_repository import (
    RepositoryArtifactPayloadRepository,
)
from app.repositories.repository_exploration_repository import RepositoryExplorationRepository
from app.repositories.repository_triage_repository import RepositoryTriageRepository
from app.repositories.synthesis_repository import SynthesisRepository
from app.services.agent_event_service import AgentEventService
from app.services.artifact_storage_status_service import ArtifactStorageStatusService
from app.services.agent_config_service import AgentConfigService
from app.services.agent_operator_service import AgentOperatorService
from app.services.backfill_timeline_service import BackfillTimelineService
from app.services.idea_family_service import IdeaFamilyService
from app.services.intake_runtime_service import GatewayIntakeRuntimeService
from app.services.memory_service import MemoryService
from app.services.obsession_service import ObsessionService
from app.services.openclaw.contract_service import GatewayContractService
from app.services.overlord_service import OverlordService, OverlordSettings
from app.models import EventSeverity
from app.services.repository_curation_service import RepositoryCurationService
from app.services.repository_exploration_service import RepositoryExplorationService
from app.services.repository_triage_service import RepositoryTriageService
from app.services.settings_service import SettingsService
from app.services.synthesis_service import SynthesisService


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
    return GatewayContractService(
        intake_runtime_service=intake_runtime_service,
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )


def get_repository_triage_service(
    session: Session = Depends(get_db_session),
) -> RepositoryTriageService:
    return RepositoryTriageService(RepositoryTriageRepository(session))


def get_agent_event_service(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AgentEventService:
    return AgentEventService(
        AgentEventRepository(session),
        broadcaster=get_event_broadcaster(request),
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )


def get_agent_operator_service(
    session: Session = Depends(get_db_session),
) -> AgentOperatorService:
    return AgentOperatorService(AgentEventRepository(session))


def get_overlord_service(
    session: Session = Depends(get_db_session),
) -> OverlordService:
    return OverlordService(
        session=session,
        gateway_contract_service=get_gateway_contract_service(session),
        settings=OverlordSettings(
            auto_remediation_enabled=settings.OVERLORD_AUTO_REMEDIATION_ENABLED,
            safe_pause_enabled=settings.OVERLORD_SAFE_PAUSE_ENABLED,
            safe_resume_enabled=settings.OVERLORD_SAFE_RESUME_ENABLED,
            stale_state_cleanup_enabled=settings.OVERLORD_STALE_STATE_CLEANUP_ENABLED,
            telegram_enabled=settings.OVERLORD_TELEGRAM_ENABLED,
            telegram_bot_token=(
                settings.OVERLORD_TELEGRAM_BOT_TOKEN.get_secret_value()
                if settings.OVERLORD_TELEGRAM_BOT_TOKEN
                else None
            ),
            telegram_chat_id=settings.OVERLORD_TELEGRAM_CHAT_ID,
            telegram_min_severity=EventSeverity(settings.OVERLORD_TELEGRAM_MIN_SEVERITY),
            telegram_daily_digest_enabled=settings.OVERLORD_TELEGRAM_DAILY_DIGEST_ENABLED,
            evaluation_interval_seconds=settings.OVERLORD_EVALUATION_INTERVAL_SECONDS,
        ),
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )


def get_artifact_storage_status_service(
    session: Session = Depends(get_db_session),
) -> ArtifactStorageStatusService:
    return ArtifactStorageStatusService(
        session,
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )


def get_event_broadcaster(request: Request) -> EventBroadcaster:
    broadcaster = getattr(request.app.state, "event_broadcaster", None)
    if not isinstance(broadcaster, EventBroadcaster):
        raise RuntimeError("Event broadcaster has not been initialized.")
    return broadcaster


def get_repository_exploration_service(
    session: Session = Depends(get_db_session),
) -> RepositoryExplorationService:
    return RepositoryExplorationService(
        RepositoryExplorationRepository(session),
        RepositoryArtifactPayloadRepository(
            session,
            runtime_dir=settings.AGENTIC_RUNTIME_DIR,
        ),
    )


def get_repository_curation_service(
    session: Session = Depends(get_db_session),
) -> RepositoryCurationService:
    return RepositoryCurationService(RepositoryCurationRepository(session))


def get_idea_family_service(
    session: Session = Depends(get_db_session),
) -> IdeaFamilyService:
    return IdeaFamilyService(IdeaFamilyRepository(session))


def get_synthesis_service(
    session: Session = Depends(get_db_session),
) -> SynthesisService:
    return SynthesisService(
        SynthesisRepository(session),
        IdeaFamilyRepository(session),
        session,
    )


def get_obsession_service(
    session: Session = Depends(get_db_session),
) -> ObsessionService:
    return ObsessionService(
        ObsessionRepository(session),
        IdeaFamilyRepository(session),
        SynthesisRepository(session),
    )


def get_memory_service(
    session: Session = Depends(get_db_session),
) -> MemoryService:
    return MemoryService(
        MemoryRepository(session),
        ObsessionRepository(session),
    )


def get_settings_service() -> SettingsService:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    return SettingsService(app_settings=Settings(_env_file=env_path))


def get_agent_config_service() -> AgentConfigService:
    return AgentConfigService()


def get_backfill_timeline_service(
    session: Session = Depends(get_db_session),
) -> BackfillTimelineService:
    return BackfillTimelineService(
        session,
        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
    )
