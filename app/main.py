"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.database import init_db
from app.logging_config import setup_logging
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.conversations import router as conversations_router
from app.routers.documents import router as documents_router

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

    # Enable CORS for browser GUI client compatibility
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    return application


app = create_app()
