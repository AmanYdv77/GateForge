from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError as RedisConnectionError

import gateforge.core.redis as redis_module
from gateforge.core.config import Settings
from gateforge.core.redis import (
    close_redis_pool,
    get_redis,
    get_redis_client,
    get_redis_pool,
    verify_redis_connection,
)


@pytest.fixture(autouse=True)
async def cleanup_redis_pool():
    """Ensure Redis pool is cleanly reset before and after each test."""
    await close_redis_pool()
    yield
    await close_redis_pool()


def test_get_redis_pool_singleton():
    """Verify that get_redis_pool caches and returns the same singleton pool instance."""
    pool1 = get_redis_pool()
    pool2 = get_redis_pool()
    assert isinstance(pool1, ConnectionPool)
    assert pool1 is pool2


def test_get_redis_pool_custom_settings():
    """Verify pool initialization respects custom configuration values."""
    custom_settings = Settings(
        REDIS_URL="redis://127.0.0.1:6380/2",
        REDIS_MAX_CONNECTIONS=10,
    )
    pool = get_redis_pool(custom_settings)
    assert pool.max_connections == 10
    assert pool.connection_kwargs.get("decode_responses") is True


def test_get_redis_client_initialization():
    """Verify get_redis_client instantiates an async Redis client bound to the pool."""
    client = get_redis_client()
    assert isinstance(client, Redis)
    assert client.connection_pool is get_redis_pool()


async def test_verify_redis_connection_success():
    """Verify verify_redis_connection returns True when ping probe succeeds."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.aclose = AsyncMock()

    with patch("gateforge.core.redis.get_redis_client", return_value=mock_client):
        healthy = await verify_redis_connection()
        assert healthy is True
        mock_client.ping.assert_awaited_once()
        mock_client.aclose.assert_awaited_once()


async def test_verify_redis_connection_failure():
    """Verify verify_redis_connection returns False when connection cannot be established."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(side_effect=RedisConnectionError("Connection refused"))
    mock_client.aclose = AsyncMock()

    with patch("gateforge.core.redis.get_redis_client", return_value=mock_client):
        healthy = await verify_redis_connection()
        assert healthy is False
        mock_client.ping.assert_awaited_once()
        mock_client.aclose.assert_awaited_once()


async def test_close_redis_pool_disconnect():
    """Verify close_redis_pool properly disconnects active connections and resets pool."""
    pool = get_redis_pool()
    with patch.object(pool, "disconnect", new_callable=AsyncMock) as mock_disconnect:
        await close_redis_pool()
        mock_disconnect.assert_awaited_once_with(inuse_connections=True)
        assert redis_module._redis_pool is None


async def test_get_redis_dependency_lifecycle():
    """Verify FastAPI dependency yields a Redis client and properly awaits closure."""
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()

    with patch("gateforge.core.redis.get_redis_client", return_value=mock_client):
        generator = get_redis()
        yielded_client = await anext(generator)
        assert yielded_client is mock_client
        mock_client.aclose.assert_not_called()

        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        mock_client.aclose.assert_awaited_once()
