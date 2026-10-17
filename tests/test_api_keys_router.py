import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateforge.core.database import get_db_session
from gateforge.main import create_app
from gateforge.models.base import Base


@pytest.fixture
async def app_with_db():  # type: ignore[no-untyped-def]
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async def override_get_db() -> Any:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    yield app

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_create_api_key_endpoint(app_with_db: Any) -> None:
    """Verify POST /api/v1/keys creates key and returns raw secret once."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        payload = {
            "name": "Integration Test Key",
            "scopes": ["read:users", "write:users"],
            "custom_rate_limit_rpm": 500,
        }
        response = await client.post("/api/v1/keys", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Integration Test Key"
        assert "raw_key" in data
        assert data["raw_key"].startswith("gfg_live_")
        assert "masked_display" in data
        assert "••••" in data["masked_display"]
        assert data["is_active"] is True
        assert data["custom_rate_limit_rpm"] == 500


@pytest.mark.asyncio
async def test_list_and_get_api_keys(app_with_db: Any) -> None:
    """Verify GET /api/v1/keys lists keys safely without exposing raw secrets."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        # Create a key first
        create_res = await client.post(
            "/api/v1/keys",
            json={"name": "Secondary Key", "scopes": ["read:metrics"]},
        )
        assert create_res.status_code == 201
        created_key = create_res.json()
        key_id = created_key["id"]

        # List keys
        list_res = await client.get("/api/v1/keys")
        assert list_res.status_code == 200
        keys_list = list_res.json()
        assert len(keys_list) >= 1

        # Security assertion: raw_key must NEVER appear in list response
        for k in keys_list:
            assert "raw_key" not in k
            assert "masked_display" in k

        # Get specific key
        get_res = await client.get(f"/api/v1/keys/{key_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == key_id
        assert get_data["name"] == "Secondary Key"
        assert "raw_key" not in get_data


@pytest.mark.asyncio
async def test_revoke_api_key_endpoint(app_with_db: Any) -> None:
    """Verify PATCH /api/v1/keys/{id}/revoke transitions key to inactive and sets revoked_at."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as client:
        create_res = await client.post(
            "/api/v1/keys",
            json={"name": "Doomed Key"},
        )
        assert create_res.status_code == 201
        key_id = create_res.json()["id"]

        # Revoke the key
        revoke_res = await client.patch(f"/api/v1/keys/{key_id}/revoke")
        assert revoke_res.status_code == 200
        revoked_data = revoke_res.json()
        assert revoked_data["id"] == key_id
        assert revoked_data["is_active"] is False
        assert revoked_data["revoked_at"] is not None

        # Non-existent key revocation returns 404
        random_uuid = str(uuid.uuid4())
        bad_revoke = await client.patch(f"/api/v1/keys/{random_uuid}/revoke")
        assert bad_revoke.status_code == 404
