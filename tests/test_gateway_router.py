from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.main import app


async def test_gateway_verify_missing_header():
    """Verify 401 when X-API-Key header is absent on gateway verification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/gateway/verify")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "ApiKey"


async def test_gateway_verify_invalid_prefix():
    """Verify 401 when X-API-Key header has invalid prefix."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": "invalid_prefix_123456789012345678901234567890"},
        )
        assert response.status_code == 401
        assert "Invalid API key prefix" in response.json()["detail"]


async def test_gateway_verify_success():
    """Verify 200 OK and accurate diagnostic metadata when key is successfully authenticated."""
    key_id = uuid4()
    user_id = uuid4()
    mock_auth_key = AuthenticatedKey(
        key_id=key_id,
        user_id=user_id,
        scopes=["read:reports", "write:webhooks"],
        rate_limit_rpm=600,
        cache_hit=True,
    )

    app.dependency_overrides[get_current_api_key] = lambda: mock_auth_key

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/gateway/verify",
                headers={"X-API-Key": "gfg_live_sampletoken123456789012345678901234"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["key_id"] == str(key_id)
            assert data["user_id"] == str(user_id)
            assert data["scopes"] == ["read:reports", "write:webhooks"]
            assert data["rate_limit_rpm"] == 600
            assert data["cache_hit"] is True
            assert "timestamp" in data
    finally:
        app.dependency_overrides.clear()
