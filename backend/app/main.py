import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.routes import gateway, health, repositories, settings as settings_routes
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.common import ErrorEnvelope, ErrorDetails

# Configure root logger
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agentic-Workflow API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
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
app.include_router(repositories.router, prefix=settings.API_V1_STR)
app.include_router(settings_routes.router, prefix=settings.API_V1_STR)
