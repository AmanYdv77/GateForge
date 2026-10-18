from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from gateforge.api.dependencies.auth import (
    AuthenticatedKey,
    get_auth_cache_service,
    get_current_api_key,
)
from gateforge.core.security import hash_api_key
from gateforge.models.api_key import APIKey
from gateforge.schemas.cache import CachedKeyData
from gateforge.services.auth_cache import AuthCacheService


@pytest.fixture
def mock_cache_service():
    mock = MagicMock(spec=AuthCacheService)
    mock.get_cached_key = AsyncMock()
    mock.set_cached_key = AsyncMock()
    return mock


@pytest.fixture
def mock_db_session():
    return AsyncMock()


async def test_get_current_api_key_cache_hit(mock_cache_service, mock_db_session):
    """Verify tier 1 cache hit returns AuthenticatedKey without database query."""
    raw_key = "gfg_live_validkey12345678901234567890123456"
    key_hash = hash_api_key(raw_key)
    key_id = uuid4()
    user_id = uuid4()

    mock_cache_service.get_cached_key.return_value = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:orders"],
        rate_limit_rpm=600,
    )

    auth_key = await get_current_api_key(
        raw_key=raw_key,
        db=mock_db_session,
        cache_service=mock_cache_service,
    )

    assert isinstance(auth_key, AuthenticatedKey)
    assert auth_key.key_id == key_id
    assert auth_key.user_id == user_id
    assert auth_key.cache_hit is True
    assert auth_key.scopes == ["read:orders"]
    assert auth_key.rate_limit_rpm == 600

    mock_cache_service.get_cached_key.assert_awaited_once_with(key_hash)
    mock_db_session.execute.assert_not_called()


async def test_get_current_api_key_cache_hit_revoked(mock_cache_service, mock_db_session):
    """Verify cache hit for inactive/revoked key raises 401 Unauthorized."""
    raw_key = "gfg_live_revokedkey1234567890123456789012"
    mock_cache_service.get_cached_key.return_value = CachedKeyData(
        key_id=uuid4(),
        user_id=uuid4(),
        is_active=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_api_key(
            raw_key=raw_key,
            db=mock_db_session,
            cache_service=mock_cache_service,
        )

    assert exc_info.value.status_code == 401
    assert "revoked or expired" in exc_info.value.detail


async def test_get_current_api_key_cache_miss_db_fallback(mock_cache_service, mock_db_session):
    """Verify tier 2 cache miss queries DB, warms cache, and returns AuthenticatedKey."""
    raw_key = "gfg_live_dbfallbackkey1234567890123456789"
    key_id = uuid4()
    user_id = uuid4()
    mock_cache_service.get_cached_key.return_value = None

    db_entity = APIKey(
        id=key_id,
        user_id=user_id,
        name="DB Fallback Key",
        key_hash=hash_api_key(raw_key),
        key_prefix="gfg_live_dbf",
        key_suffix="6789",
        custom_rate_limit_rpm=60,
        scopes=["read:data"],
        is_active=True,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    with patch(
        "gateforge.api.dependencies.auth.APIKeyService.get_by_hash",
        new_callable=AsyncMock,
        return_value=db_entity,
    ) as mock_get_by_hash:
        auth_key = await get_current_api_key(
            raw_key=raw_key,
            db=mock_db_session,
            cache_service=mock_cache_service,
        )

        assert auth_key.key_id == key_id
        assert auth_key.cache_hit is False
        mock_get_by_hash.assert_awaited_once()
        mock_cache_service.set_cached_key.assert_awaited_once()


async def test_get_current_api_key_cache_miss_not_found(mock_cache_service, mock_db_session):
    """Verify 401 when key is absent from both cache and database."""
    raw_key = "gfg_live_unknownkey1234567890123456789012"
    mock_cache_service.get_cached_key.return_value = None

    with patch(
        "gateforge.api.dependencies.auth.APIKeyService.get_by_hash",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_api_key(
                raw_key=raw_key,
                db=mock_db_session,
                cache_service=mock_cache_service,
            )

        assert exc_info.value.status_code == 401
        assert "Invalid or unrecognized" in exc_info.value.detail


async def test_get_current_api_key_cache_miss_db_revoked(mock_cache_service, mock_db_session):
    """Verify 401 when key in database has is_active=False."""
    raw_key = "gfg_live_dbrevokedkey12345678901234567890"
    mock_cache_service.get_cached_key.return_value = None

    db_entity = APIKey(
        id=uuid4(),
        user_id=uuid4(),
        name="Revoked Key",
        key_hash=hash_api_key(raw_key),
        key_prefix="gfg_live_dbr",
        key_suffix="7890",
        is_active=False,
    )

    with patch(
        "gateforge.api.dependencies.auth.APIKeyService.get_by_hash",
        new_callable=AsyncMock,
        return_value=db_entity,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_api_key(
                raw_key=raw_key,
                db=mock_db_session,
                cache_service=mock_cache_service,
            )

        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail


def test_get_auth_cache_service_factory():
    """Verify factory returns an AuthCacheService instance."""
    service = get_auth_cache_service()
    assert isinstance(service, AuthCacheService)
