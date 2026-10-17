import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from gateforge.core.redis import get_redis_client

logger = structlog.get_logger(__name__)


class ResilientRedisClient:
    """Resilient Redis client wrapper providing timeout safeguards, retries, and soft degradation."""

    def __init__(
        self,
        redis_client: Redis | None = None,
        default_timeout_seconds: float = 1.0,
        max_retries: int = 2,
        initial_backoff_seconds: float = 0.05,
    ) -> None:
        self._client: Redis = redis_client or get_redis_client()
        self._timeout: float = default_timeout_seconds
        self._max_retries: int = max_retries
        self._initial_backoff: float = initial_backoff_seconds

    async def _execute_with_retry(
        self,
        operation_name: str,
        coro_func: Callable[[], Awaitable[Any]],
        fallback_value: Any = None,
    ) -> Any:
        """Execute an async Redis operation with timeout enforcement and exponential backoff."""
        delay = self._initial_backoff
        for attempt in range(1, self._max_retries + 1):
            try:
                return await asyncio.wait_for(coro_func(), timeout=self._timeout)
            except TimeoutError:
                logger.warning(
                    "redis_operation_timeout",
                    operation=operation_name,
                    attempt=attempt,
                    timeout_seconds=self._timeout,
                )
                if attempt == self._max_retries:
                    return fallback_value
            except (RedisError, OSError) as exc:
                logger.warning(
                    "redis_transient_error",
                    operation=operation_name,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == self._max_retries:
                    return fallback_value

            await asyncio.sleep(delay)
            delay *= 2

        return fallback_value

    async def get(self, key: str) -> str | None:
        """Retrieve a string value by key with safe fallback to None on Redis outages."""
        val = await self._execute_with_retry(
            operation_name="get",
            coro_func=lambda: self._client.get(key),
            fallback_value=None,
        )
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return str(val)

    async def setex(self, key: str, time_seconds: int, value: str) -> bool:
        """Store a key with expiration in seconds with safe failure fallback."""
        result = await self._execute_with_retry(
            operation_name="setex",
            coro_func=lambda: self._client.setex(key, time_seconds, value),
            fallback_value=False,
        )
        return bool(result)

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys safely, returning number of deleted keys or 0 on failure."""
        if not keys:
            return 0
        result = await self._execute_with_retry(
            operation_name="delete",
            coro_func=lambda: self._client.delete(*keys),
            fallback_value=0,
        )
        return int(result) if result else 0

    async def exists(self, *keys: str) -> int:
        """Check if one or more keys exist in Redis safely."""
        if not keys:
            return 0
        result = await self._execute_with_retry(
            operation_name="exists",
            coro_func=lambda: self._client.exists(*keys),
            fallback_value=0,
        )
        return int(result) if result else 0

    async def ping(self) -> bool:
        """Check Redis connectivity safely."""
        result = await self._execute_with_retry(
            operation_name="ping",
            coro_func=lambda: self._client.ping(),
            fallback_value=False,
        )
        return bool(result)

    async def aclose(self) -> None:
        """Close client resources."""
        await self._client.aclose()


def get_resilient_redis(redis_client: Redis | None = None) -> ResilientRedisClient:
    """Factory creating a configured ResilientRedisClient instance."""
    return ResilientRedisClient(redis_client=redis_client)
