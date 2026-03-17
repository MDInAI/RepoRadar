import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import agents, events_stream, gateway, health, idea_families, incidents, memory, obsession, overlord, overview, repositories, settings as settings_routes, synthesis
from app.api.deps import get_overlord_service
from app.core.config import settings
from app.core.database import engine
from app.core.event_bridge_health import EventBridgeHealth
from app.core.errors import AppError
from app.core.event_broadcaster import EventBroadcaster
from app.repositories.agent_event_repository import AgentEventRepository
from app.schemas.common import ErrorEnvelope, ErrorDetails
from app.services.agent_event_service import AgentEventService

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def bridge_persisted_events(app: FastAPI) -> None:
    last_event_id: int | None = None
    broadcaster = app.state.event_broadcaster
    event_bridge_health = app.state.event_bridge_health

    while True:
        try:
            with Session(engine) as session:
                service = AgentEventService(
                    AgentEventRepository(
                        session,
                        runtime_dir=settings.AGENTIC_RUNTIME_DIR,
                    ),
                    broadcaster=broadcaster,
                    runtime_dir=settings.AGENTIC_RUNTIME_DIR,
                )
                if last_event_id is None:
                    last_event_id = service.get_latest_system_event_id()
                else:
                    last_event_id = service.bridge_new_events(after_event_id=last_event_id)
            event_bridge_health.record_success(last_event_id)
        except Exception as exc:
            event_bridge_health.record_failure(exc)
            logger.exception("Failed to bridge persisted system events into the SSE stream.")

        await asyncio.sleep(settings.EVENT_BRIDGE_POLL_INTERVAL_SECONDS)


async def run_overlord_control_loop(app: FastAPI) -> None:
    while True:
        try:
            with Session(engine) as session:
                service = get_overlord_service(session)
                service.evaluate_and_remediate()
        except Exception:
            logger.exception("Overlord control loop failed during evaluation.")
        await asyncio.sleep(settings.OVERLORD_EVALUATION_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.event_bridge_health = EventBridgeHealth()
    app.state.event_broadcaster = EventBroadcaster(
        max_subscribers=settings.EVENT_STREAM_MAX_SUBSCRIBERS,
        queue_maxsize=settings.EVENT_STREAM_SUBSCRIBER_QUEUE_SIZE,
    )
    bridge_task = asyncio.create_task(bridge_persisted_events(app))
    overlord_task = asyncio.create_task(run_overlord_control_loop(app))
    try:
        yield
    finally:
        overlord_task.cancel()
        bridge_task.cancel()
        with suppress(asyncio.CancelledError):
            await overlord_task
        with suppress(asyncio.CancelledError):
            await bridge_task

app = FastAPI(
    title="Agentic-Workflow API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Standard CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global custom error handler for AppError
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(f"AppError at {request.url.path}: {exc.message} (code: {exc.code})")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(
            error=ErrorDetails(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
        ).model_dump(),
    )


# Handle Pydantic validation errors with structured error envelope
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error at {request.url.path}: {exc.errors()}")

    # Serialize errors properly - convert ValueError objects to strings
    serializable_errors = []
    for error in exc.errors():
        error_dict = dict(error)
        if "ctx" in error_dict and error_dict["ctx"]:
            # Convert any non-serializable objects in ctx to strings
            error_dict["ctx"] = {k: str(v) for k, v in error_dict["ctx"].items()}
        serializable_errors.append(error_dict)

    return JSONResponse(
        status_code=422,
        content=ErrorEnvelope(
            error=ErrorDetails(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": serializable_errors},
            ),
        ).model_dump(),
    )


# Global catch-all for 500s
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url.path}")
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error=ErrorDetails(
                code="internal_error",
                message="An unexpected internal error occurred.",
            ),
        ).model_dump(),
    )


# Include routes
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(gateway.router, prefix=settings.API_V1_STR)
app.include_router(agents.router, prefix=settings.API_V1_STR, tags=["agents"])
app.include_router(events_stream.router, prefix=settings.API_V1_STR, tags=["events"])
app.include_router(idea_families.router, prefix=f"{settings.API_V1_STR}/idea-families", tags=["idea-families"])
app.include_router(incidents.router, prefix=settings.API_V1_STR, tags=["incidents"])
app.include_router(memory.router, prefix=settings.API_V1_STR, tags=["memory"])
app.include_router(obsession.router, prefix=f"{settings.API_V1_STR}/obsession", tags=["obsession"])
app.include_router(overlord.router, prefix=settings.API_V1_STR, tags=["overlord"])
app.include_router(overview.router, prefix=settings.API_V1_STR, tags=["overview"])
app.include_router(repositories.router, prefix=settings.API_V1_STR)
app.include_router(settings_routes.router, prefix=settings.API_V1_STR)
app.include_router(synthesis.router, prefix=f"{settings.API_V1_STR}/synthesis", tags=["synthesis"])
