from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.api.dependencies.auth import get_auth_cache_service
from gateforge.api.deps import get_current_user
from gateforge.core.database import get_db_session
from gateforge.main import app
from gateforge.models.api_key import APIKey
from gateforge.models.user import User
from gateforge.services.api_key import APIKeyService
from gateforge.services.auth_cache import AuthCacheService


@pytest.fixture
def mock_cache_service():
    mock = MagicMock(spec=AuthCacheService)
    mock.invalidate_key_by_hash = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_user():
    return User(
        id=uuid4(),
        email="dev@gateforge.internal",
        hashed_password="hash",
        tier="enterprise",
    )


async def test_service_revoke_key_purges_cache(mock_cache_service):
    """Verify APIKeyService.revoke_key directly invalidates key hash in cache."""
    key_id = uuid4()
    key_hash = "abcdef" * 10 + "1234"

    db_key = APIKey(
        id=key_id,
        user_id=uuid4(),
        name="Key To Revoke",
        key_prefix="gfg_live_abc",
        key_suffix="1234",
        key_hash=key_hash,
        scopes=["read:all"],
        created_at=datetime.now(UTC),
        is_active=True,
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(APIKeyService, "get_by_id", AsyncMock(return_value=db_key))
        revoked = await APIKeyService.revoke_key(
            session=mock_session,
            key_id=key_id,
            cache_service=mock_cache_service,
        )

        assert revoked is not None
        assert revoked.is_active is False
        mock_cache_service.invalidate_key_by_hash.assert_awaited_once_with(key_hash)


async def test_endpoint_revoke_key_purges_cache(mock_cache_service, mock_user):
    """Verify PATCH /api/v1/keys/{key_id}/revoke triggers cache purge through HTTP layer."""
    key_id = uuid4()
    key_hash = "9999888877776666" * 4

    db_key = APIKey(
        id=key_id,
        user_id=mock_user.id,
        name="Key HTTP Revoke",
        key_prefix="gfg_live_999",
        key_suffix="6666",
        key_hash=key_hash,
        scopes=["read:reports"],
        created_at=datetime.now(UTC),
        is_active=True,
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_auth_cache_service] = lambda: mock_cache_service

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(APIKeyService, "get_by_id", AsyncMock(return_value=db_key))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(f"/api/v1/keys/{key_id}/revoke")

                assert response.status_code == 200
                data = response.json()
                assert data["is_active"] is False
                assert data["id"] == str(key_id)
                mock_cache_service.invalidate_key_by_hash.assert_awaited_once_with(key_hash)
    finally:
        app.dependency_overrides.clear()
