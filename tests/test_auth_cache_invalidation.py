from unittest.mock import AsyncMock, MagicMock

import pytest

from gateforge.core.redis_client import ResilientRedisClient
from gateforge.core.security import hash_api_key
from gateforge.schemas.cache import build_auth_cache_key
from gateforge.services.auth_cache import AuthCacheService


@pytest.fixture
def mock_redis_client():
    mock = MagicMock(spec=ResilientRedisClient)
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def auth_cache_service(mock_redis_client):
    return AuthCacheService(redis_client=mock_redis_client)


async def test_invalidate_key_by_hash(auth_cache_service, mock_redis_client):
    """Verify single hash invalidation issues delete to correct namespaced Redis key."""
    key_hash = "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"
    mock_redis_client.delete.return_value = 1

    success = await auth_cache_service.invalidate_key_by_hash(key_hash)
    assert success is True
    mock_redis_client.delete.assert_awaited_once_with(build_auth_cache_key(key_hash))


async def test_invalidate_key_by_hash_not_found(auth_cache_service, mock_redis_client):
    """Verify single hash invalidation returns False if key was not present in cache."""
    key_hash = "abcdef" * 10 + "1234"
    mock_redis_client.delete.return_value = 0

    success = await auth_cache_service.invalidate_key_by_hash(key_hash)
    assert success is False
    mock_redis_client.delete.assert_awaited_once_with(build_auth_cache_key(key_hash))


async def test_invalidate_keys_by_hashes_batch(auth_cache_service, mock_redis_client):
    """Verify batch invalidation constructs multiple Redis keys for atomic delete."""
    hashes = [
        "hash_one_64characterslongstringpadding0000000000000000000000000000",
        "hash_two_64characterslongstringpadding0000000000000000000000000000",
    ]
    mock_redis_client.delete.return_value = 2

    deleted_count = await auth_cache_service.invalidate_keys_by_hashes(hashes)
    assert deleted_count == 2
    mock_redis_client.delete.assert_awaited_once_with(
        build_auth_cache_key(hashes[0]),
        build_auth_cache_key(hashes[1]),
    )


async def test_invalidate_keys_by_hashes_empty(auth_cache_service, mock_redis_client):
    """Verify batch invalidation returns 0 immediately if list is empty."""
    deleted_count = await auth_cache_service.invalidate_keys_by_hashes([])
    assert deleted_count == 0
    mock_redis_client.delete.assert_not_called()


async def test_invalidate_key_convenience_raw_token(auth_cache_service, mock_redis_client):
    """Verify invalidate_key correctly hashes raw key before deleting from cache."""
    raw_token = "gfg_live_abcdef12345678901234567890123456"
    expected_hash = hash_api_key(raw_token)
    mock_redis_client.delete.return_value = 1

    success = await auth_cache_service.invalidate_key(raw_token)
    assert success is True
    mock_redis_client.delete.assert_awaited_once_with(build_auth_cache_key(expected_hash))
