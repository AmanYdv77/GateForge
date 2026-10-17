from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateforge.core.config import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and graceful shutdown hooks."""
    # Startup hooks: DB pools and Redis connection pools will be attached here
    yield
    # Shutdown hooks: Graceful pool teardown will execute here


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

    return app


app = create_app()
