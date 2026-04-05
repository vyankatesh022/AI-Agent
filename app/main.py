"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.database import init_db
from app.logging_config import setup_logging
from app.observability.middleware import ObservabilityMiddleware
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.conversations import router as conversations_router
from app.routers.documents import router as documents_router
from app.security.errors import AppSecurityException, ErrorCode, RateLimitExceededError
from app.security.headers import SecurityHeadersMiddleware
from app.security.request_size import RequestSizeLimitMiddleware

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Response schema for service health status."""

    status: str = Field(description="Operational status of the service")
    service: str = Field(description="Name of the service")
    version: str = Field(description="Current version of the service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        "Application starting: %s v%s [env=%s]",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )
    # Ensure database schema is initialized
    init_db()
    logger.info("Database initialization completed")
    yield
    logger.info("Application shutdown completed: %s", settings.APP_NAME)


def create_app() -> FastAPI:
    """Application factory for configuring and instantiating the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Production-ready AI Agent Backend foundation.",
        lifespan=lifespan,
    )

    # Configure CORS allowlist
    cors_origins = [
        o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()
    ]
    if not cors_origins:
        cors_origins = ["*"]
    allow_credentials = "*" not in cors_origins

    # Middlewares run in reverse order of addition:
    # 1. RequestSizeLimitMiddleware (rejects payloads > 15MB)
    # 2. SecurityHeadersMiddleware (nosniff, clickjacking, CSP)
    # 3. ObservabilityMiddleware (X-Request-ID, latency timing, logging)
    # 4. CORSMiddleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(ObservabilityMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestSizeLimitMiddleware)

    # Security exception handlers
    @application.exception_handler(AppSecurityException)
    async def security_exception_handler(
        request: Request, exc: AppSecurityException
    ) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitExceededError):
            headers["Retry-After"] = str(exc.retry_after_seconds)
            headers["X-Error-Code"] = exc.error_code.value
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code.value},
            headers=headers,
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        headers = dict(exc.headers or {})
        content: dict[str, str] = {"detail": str(exc.detail)}
        if "X-Error-Code" in headers:
            content["error_code"] = headers["X-Error-Code"]
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=headers,
        )

    @application.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled server error on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred.",
                "error_code": ErrorCode.INTERNAL_ERROR.value,
            },
        )

    # Register routers
    application.include_router(auth_router)
    application.include_router(conversations_router)
    application.include_router(agent_router)
    application.include_router(documents_router)

    # Mount static frontend GUI if present
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.exists():
        application.mount(
            "/ui",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="ui",
        )

        @application.get("/", include_in_schema=False)
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/ui/")

    @application.get(
        "/health",
        response_model=HealthResponse,
        summary="Service Health Check",
        description="Returns the operational status, service name, and version.",
        tags=["System"],
    )
    async def health_check(
        current_settings: Annotated[Settings, Depends(get_settings)],
    ) -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=current_settings.APP_NAME,
            version=current_settings.APP_VERSION,
        )

    @application.get(
        "/ready",
        summary="Service Readiness Probe",
        description="Verifies database connectivity without triggering external LLM calls.",
        tags=["System"],
    )
    async def readiness_check() -> JSONResponse:
        try:
            from sqlalchemy import text

            from app.database import get_engine

            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse(
                status_code=200,
                content={"status": "ready", "database": "connected"},
            )
        except Exception as exc:
            logger.error("Readiness check failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "disconnected",
                    "detail": "Database connectivity check failed",
                },
            )

    return application


app = create_app()
