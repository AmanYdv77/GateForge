from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from gateforge.core.config import Settings
from gateforge.core.redis_client import ResilientRedisClient
from gateforge.schemas.cache import CachedKeyData, build_auth_cache_key
from gateforge.services.auth_cache import AuthCacheService


@pytest.fixture
def mock_redis_client():
    mock = MagicMock(spec=ResilientRedisClient)
    mock.get = AsyncMock()
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def auth_cache_service(mock_redis_client):
    settings = Settings(AUTH_CACHE_TTL_SECONDS=300)
    return AuthCacheService(
        redis_client=mock_redis_client,
        settings=settings,
        jitter_max_seconds=30,
    )


def test_calculate_ttl_with_jitter(auth_cache_service):
    """Verify jitter produces TTL within [base, base + jitter_max]."""
    for _ in range(20):
        ttl = auth_cache_service.calculate_ttl(base_ttl=300)
        assert 300 <= ttl <= 330


def test_calculate_ttl_zero_jitter(mock_redis_client):
    """Verify zero jitter returns exact base TTL without variance."""
    service = AuthCacheService(
        redis_client=mock_redis_client,
        jitter_max_seconds=0,
    )
    assert service.calculate_ttl(base_ttl=120) == 120


async def test_get_cached_key_hit(auth_cache_service, mock_redis_client):
    """Verify cache hit deserializes and returns CachedKeyData."""
    key_id = uuid4()
    user_id = uuid4()
    cached = CachedKeyData(key_id=key_id, user_id=user_id, scopes=["read:all"])
    mock_redis_client.get.return_value = cached.to_json()

    result = await auth_cache_service.get_cached_key("test_hash_123")
    assert result is not None
    assert result.key_id == key_id
    assert result.user_id == user_id
    assert result.scopes == ["read:all"]
    mock_redis_client.get.assert_awaited_once_with(build_auth_cache_key("test_hash_123"))


async def test_get_cached_key_miss(auth_cache_service, mock_redis_client):
    """Verify cache miss returns None."""
    mock_redis_client.get.return_value = None
    result = await auth_cache_service.get_cached_key("missing_hash")
    assert result is None


async def test_get_cached_key_corrupted_payload(auth_cache_service, mock_redis_client):
    """Verify corrupted JSON payload is caught safely and returns None."""
    mock_redis_client.get.return_value = "not_valid_json_string{["
    result = await auth_cache_service.get_cached_key("corrupt_hash")
    assert result is None


async def test_set_cached_key(auth_cache_service, mock_redis_client):
    """Verify set_cached_key stores serialized payload with jittered expiration."""
    mock_redis_client.setex.return_value = True
    key_id = uuid4()
    user_id = uuid4()
    data = CachedKeyData(key_id=key_id, user_id=user_id)

    success = await auth_cache_service.set_cached_key("hash_abc", data, ttl_seconds=600)
    assert success is True
    mock_redis_client.setex.assert_awaited_once()
    args, _ = mock_redis_client.setex.await_args
    assert args[0] == build_auth_cache_key("hash_abc")
    assert 600 <= args[1] <= 630
    assert str(key_id) in args[2]


async def test_get_or_set_cached_key_read_through(auth_cache_service, mock_redis_client):
    """Verify read-through pattern: cache miss triggers producer and warms cache."""
    # 1. First invocation: cache miss -> producer called -> warmed in Redis
    mock_redis_client.get.return_value = None
    mock_redis_client.setex.return_value = True

    key_id = uuid4()
    producer_data = CachedKeyData(key_id=key_id, user_id=uuid4())
    mock_producer = AsyncMock(return_value=producer_data)

    res1 = await auth_cache_service.get_or_set_cached_key("hash_rt", mock_producer)
    assert res1 is producer_data
    mock_producer.assert_awaited_once()
    mock_redis_client.setex.assert_awaited_once()

    # 2. Second invocation: cache hit -> producer skipped
    mock_redis_client.get.return_value = producer_data.to_json()
    mock_producer.reset_mock()

    res2 = await auth_cache_service.get_or_set_cached_key("hash_rt", mock_producer)
    assert res2 is not None
    assert res2.key_id == key_id
    mock_producer.assert_not_called()
