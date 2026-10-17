from collections.abc import AsyncGenerator
from typing import Any

import structlog
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from gateforge.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_redis_pool: ConnectionPool | None = None


def get_redis_pool(settings: Settings | None = None) -> ConnectionPool:
    """Initialize or return the cached singleton Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        cfg = settings or get_settings()
        logger.info(
            "initializing_redis_connection_pool",
            redis_url=cfg.REDIS_URL,
            max_connections=cfg.REDIS_MAX_CONNECTIONS,
        )
        _redis_pool = ConnectionPool.from_url(
            cfg.REDIS_URL,
            max_connections=cfg.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_pool


def get_redis_client(settings: Settings | None = None) -> Redis:
    """Create an asynchronous Redis client bound to the application pool."""
    pool = get_redis_pool(settings)
    return Redis(connection_pool=pool)


async def close_redis_pool() -> None:
    """Close all connections in the Redis pool gracefully during application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        logger.info("closing_redis_connection_pool")
        await _redis_pool.disconnect(inuse_connections=True)
        _redis_pool = None


async def verify_redis_connection(settings: Settings | None = None) -> bool:
    """Execute a ping probe to verify Redis connectivity without raising exceptions."""
    client = get_redis_client(settings)
    try:
        response = await client.ping()
        return bool(response)
    except (RedisError, OSError) as exc:
        logger.warning("redis_health_check_failed", error=str(exc))
        return False
    finally:
        await client.aclose()


async def get_redis(
    settings: Settings | None = None,
) -> AsyncGenerator[Redis, Any]:
    """FastAPI dependency yielding an active Redis client and closing client session afterwards."""
    client = get_redis_client(settings)
    try:
        yield client
    finally:
        await client.aclose()
