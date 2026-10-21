from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from service_orchestrator.application_processing.presentation.router import (
    router as applications_router,
)
from service_orchestrator.bootstrap.dependencies import Container, build_container
from service_orchestrator.config import Settings
from service_orchestrator.service_catalog.presentation.router import router as services_router
from service_orchestrator.shared.infrastructure.log_config import configure_logging
from service_orchestrator.shared.presentation.errors import register_error_handlers
from service_orchestrator.shared.presentation.middleware import (
    BodySizeLimitMiddleware,
    RequestLoggingMiddleware,
)
from service_orchestrator.shared.presentation.schemas import ApiResponse, ok


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    container = container or build_container(settings or Settings())
    configure_logging(
        container.settings.log_level, container.settings.log_format, container.settings.log_sql
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        container.engine.dispose()

    app = FastAPI(
        title="ServiceOrchestrator",
        version="0.1.0",
        summary="Define, publish, validate and process configurable services.",
        lifespan=lifespan,
    )
    app.state.container = container
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=container.settings.max_request_bytes)
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)
    app.include_router(services_router)
    app.include_router(applications_router)

    @app.get("/health", tags=["health"])
    def health() -> ApiResponse[dict[str, str]]:
        return ok({"status": "ok"})

    return app
