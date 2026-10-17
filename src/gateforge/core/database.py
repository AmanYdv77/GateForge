from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateforge.core.config import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create a configured async SQLAlchemy engine instance."""
    app_settings = settings or get_settings()

    engine_kwargs: dict[str, Any] = {
        "echo": app_settings.DEBUG,
        "pool_pre_ping": True,
    }

    # SQLite (used in fast in-memory unit tests) does not support pool_size or max_overflow
    if not app_settings.DATABASE_URL.startswith("sqlite"):
        engine_kwargs["pool_size"] = app_settings.DB_POOL_SIZE
        engine_kwargs["max_overflow"] = app_settings.DB_MAX_OVERFLOW
        engine_kwargs["pool_timeout"] = app_settings.DB_TIMEOUT_SECONDS

    return create_async_engine(app_settings.DATABASE_URL, **engine_kwargs)


engine = create_engine()

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional asynchronous database session dependency."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
