import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from gateforge.api.dependencies.api_key_header import extract_raw_api_key


@pytest.fixture
def auth_header_app():
    """Create a lightweight FastAPI app demonstrating header extraction dependency."""
    app = FastAPI()

    @app.get("/test/header")
    async def sample_protected_route(api_key: str = Depends(extract_raw_api_key)):
        return {"status": "ok", "key_received": api_key[:12] + "..."}

    return app


async def test_extract_raw_api_key_missing_header(auth_header_app):
    """Verify 401 Unauthorized with WWW-Authenticate header when X-API-Key is absent."""
    transport = ASGITransport(app=auth_header_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/header")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "ApiKey"
        assert response.json()["detail"] == "API key header 'X-API-Key' is missing"


async def test_extract_raw_api_key_invalid_prefix(auth_header_app):
    """Verify 401 when key lacks the required 'gfg_live_' prefix."""
    transport = ASGITransport(app=auth_header_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/header",
            headers={"X-API-Key": "sk_test_12345678901234567890123456789012"},
        )
        assert response.status_code == 401
        assert "Invalid API key prefix" in response.json()["detail"]


async def test_extract_raw_api_key_short_length(auth_header_app):
    """Verify 401 when key prefix is correct but token length is truncated."""
    transport = ASGITransport(app=auth_header_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/header",
            headers={"X-API-Key": "gfg_live_short"},
        )
        assert response.status_code == 401
        assert "Malformed API key length" in response.json()["detail"]


async def test_extract_raw_api_key_success(auth_header_app):
    """Verify valid key passes dependency inspection and reaches route handler."""
    valid_key = "gfg_live_abc12345678901234567890123456789012"
    transport = ASGITransport(app=auth_header_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/header",
            headers={"X-API-Key": valid_key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "gfg_live_abc" in response.json()["key_received"]
