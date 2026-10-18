from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.api.dependencies.ratelimit import get_rate_limiter
from gateforge.core.ratelimit import SlidingWindowLimiter
from gateforge.main import app
from gateforge.schemas.ratelimit import RateLimitDecision


@pytest.fixture
def mock_auth_key():
    return AuthenticatedKey(
        key_id=uuid4(),
        user_id=uuid4(),
        scopes=["read:data", "write:events"],
        rate_limit_rpm=60,
        cache_hit=True,
    )


@pytest.fixture
def mock_limiter():
    mock = MagicMock(spec=SlidingWindowLimiter)
    mock.check_rate_limit = AsyncMock()
    return mock


async def test_gateway_verify_includes_ratelimit_headers(mock_auth_key, mock_limiter):
    """Verify /gateway/verify returns identity and RFC 6585 rate limit headers."""
    mock_limiter.check_rate_limit.return_value = RateLimitDecision(
        allowed=True,
        limit=60,
        remaining=59,
        reset_seconds=60,
        retry_after_seconds=0,
    )

    app.dependency_overrides[get_current_api_key] = lambda: mock_auth_key
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter

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
            assert response.headers["x-ratelimit-limit"] == "60"
            assert response.headers["x-ratelimit-remaining"] == "59"
            assert response.headers["x-ratelimit-reset"] == "60"
    finally:
        app.dependency_overrides.clear()


async def test_gateway_echo_endpoint_success(mock_auth_key, mock_limiter):
    """Verify /gateway/echo echoes payload and decrements remaining quota."""
    mock_limiter.check_rate_limit.return_value = RateLimitDecision(
        allowed=True,
        limit=60,
        remaining=48,
        reset_seconds=35,
        retry_after_seconds=0,
    )

    app.dependency_overrides[get_current_api_key] = lambda: mock_auth_key
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/gateway/echo",
                headers={"X-API-Key": "gfg_live_sampletoken123456789012345678901234"},
                json={"payload": {"service": "payments", "amount": 100}},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["key_id"] == str(mock_auth_key.key_id)
            assert data["echo_payload"] == {"service": "payments", "amount": 100}
            assert data["remaining_quota"] == 48
            assert data["reset_seconds"] == 35
            assert response.headers["x-ratelimit-remaining"] == "48"
    finally:
        app.dependency_overrides.clear()


async def test_gateway_echo_rate_limit_exceeded(mock_auth_key, mock_limiter):
    """Verify /gateway/echo raises 429 when quota is exhausted."""
    mock_limiter.check_rate_limit.return_value = RateLimitDecision(
        allowed=False,
        limit=60,
        remaining=0,
        reset_seconds=22,
        retry_after_seconds=22,
    )

    app.dependency_overrides[get_current_api_key] = lambda: mock_auth_key
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/gateway/echo",
                headers={"X-API-Key": "gfg_live_sampletoken123456789012345678901234"},
                json={"payload": {"test": "payload"}},
            )

            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
            assert response.headers["retry-after"] == "22"
            assert response.headers["x-ratelimit-remaining"] == "0"
    finally:
        app.dependency_overrides.clear()
