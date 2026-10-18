from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateforge.api.health import router as health_router
from gateforge.api.middleware.telemetry import TelemetryMiddleware
from gateforge.api.v1.gateway import router as gateway_router
from gateforge.api.v1.keys import router as keys_router
from gateforge.core.config import Settings, get_settings
from gateforge.core.logging import setup_logging
from gateforge.core.redis import close_redis_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and graceful shutdown hooks."""
    setup_logging()
    try:
        yield
    finally:
        await close_redis_pool()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a production-ready FastAPI application instance."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title=app_settings.PROJECT_NAME,
        version="0.1.0",
        description="High-Throughput API Key Gateway, Auth Cache & Sliding-Window Rate Limiter",
        debug=app_settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if app_settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if app_settings.ENVIRONMENT != "production" else None,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if app_settings.ENVIRONMENT == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register high-precision request timing and telemetry middleware
    app.add_middleware(TelemetryMiddleware)

    # Register core routers
    app.include_router(health_router)
    app.include_router(keys_router, prefix="/api/v1")
    app.include_router(gateway_router, prefix="/api/v1")

    return app


app = create_app()
