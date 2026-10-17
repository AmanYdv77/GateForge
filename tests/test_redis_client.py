import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from gateforge.core.redis_client import ResilientRedisClient, get_resilient_redis


@pytest.fixture
def mock_raw_redis():
    """Create a mock raw Redis client."""
    mock = MagicMock()
    mock.get = AsyncMock()
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    mock.exists = AsyncMock()
    mock.ping = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def resilient_client(mock_raw_redis):
    """Create a ResilientRedisClient with minimal backoff for fast tests."""
    return ResilientRedisClient(
        redis_client=mock_raw_redis,
        default_timeout_seconds=0.1,
        max_retries=2,
        initial_backoff_seconds=0.001,
    )


async def test_resilient_get_success(resilient_client, mock_raw_redis):
    """Verify get returns the cached string value on success."""
    mock_raw_redis.get.return_value = '{"user_id": "123"}'
    result = await resilient_client.get("test:key")
    assert result == '{"user_id": "123"}'
    mock_raw_redis.get.assert_awaited_once_with("test:key")


async def test_resilient_get_timeout_fallback(resilient_client, mock_raw_redis):
    """Verify get catches TimeoutError and returns None without raising."""

    async def slow_get(*args, **kwargs):
        await asyncio.sleep(0.3)
        return "val"

    mock_raw_redis.get.side_effect = slow_get
    result = await resilient_client.get("test:key")
    assert result is None


async def test_resilient_get_connection_error_fallback(resilient_client, mock_raw_redis):
    """Verify get catches Redis connection errors and returns None."""
    mock_raw_redis.get.side_effect = RedisConnectionError("Connection dropped")
    result = await resilient_client.get("test:key")
    assert result is None
    assert mock_raw_redis.get.await_count == 2


async def test_resilient_get_retry_recovery(resilient_client, mock_raw_redis):
    """Verify get recovers and returns value if transient error succeeds on retry."""
    mock_raw_redis.get.side_effect = [
        RedisConnectionError("Transient network blip"),
        '{"recovered": true}',
    ]
    result = await resilient_client.get("test:key")
    assert result == '{"recovered": true}'
    assert mock_raw_redis.get.await_count == 2


async def test_resilient_setex_success(resilient_client, mock_raw_redis):
    """Verify setex stores key and returns True."""
    mock_raw_redis.setex.return_value = True
    result = await resilient_client.setex("key", 60, "val")
    assert result is True
    mock_raw_redis.setex.assert_awaited_once_with("key", 60, "val")


async def test_resilient_setex_failure_fallback(resilient_client, mock_raw_redis):
    """Verify setex returns False on persistent error instead of crashing caller."""
    mock_raw_redis.setex.side_effect = RedisConnectionError("Outage")
    result = await resilient_client.setex("key", 60, "val")
    assert result is False


async def test_resilient_delete_operations(resilient_client, mock_raw_redis):
    """Verify delete handles single, multiple, and empty key deletions."""
    # Empty keys
    zero = await resilient_client.delete()
    assert zero == 0
    mock_raw_redis.delete.assert_not_called()

    # Successful deletion
    mock_raw_redis.delete.return_value = 2
    deleted = await resilient_client.delete("k1", "k2")
    assert deleted == 2
    mock_raw_redis.delete.assert_awaited_once_with("k1", "k2")


async def test_resilient_exists_and_ping(resilient_client, mock_raw_redis):
    """Verify exists and ping wrappers function properly."""
    mock_raw_redis.exists.return_value = 1
    mock_raw_redis.ping.return_value = True

    assert await resilient_client.exists("k1") == 1
    assert await resilient_client.ping() is True


async def test_resilient_aclose_and_factory(resilient_client, mock_raw_redis):
    """Verify aclose resource cleanup and factory helper."""
    await resilient_client.aclose()
    mock_raw_redis.aclose.assert_awaited_once()

    factory_client = get_resilient_redis(mock_raw_redis)
    assert isinstance(factory_client, ResilientRedisClient)
