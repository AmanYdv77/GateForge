from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.api.dependencies.ratelimit import (
    enforce_rate_limit,
    get_rate_limiter,
)
from gateforge.core.ratelimit import SlidingWindowLimiter
from gateforge.schemas.ratelimit import RateLimitDecision


@pytest.fixture
def mock_auth_key():
    return AuthenticatedKey(
        key_id=uuid4(),
        user_id=uuid4(),
        scopes=["read:data"],
        rate_limit_rpm=60,
        cache_hit=True,
    )


@pytest.fixture
def mock_limiter():
    mock = MagicMock(spec=SlidingWindowLimiter)
    mock.check_rate_limit = AsyncMock()
    return mock


@pytest.fixture
def test_app(mock_auth_key, mock_limiter):
    app = FastAPI()

    @app.get("/test/rate-limited", dependencies=[Depends(enforce_rate_limit)])
    async def sample_endpoint():
        return {"status": "ok"}

    app.dependency_overrides[get_current_api_key] = lambda: mock_auth_key
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter
    return app


async def test_enforce_rate_limit_allowed_injects_headers(test_app, mock_limiter):
    """Verify within-quota requests receive standard RFC 6585 rate limit headers."""
    mock_limiter.check_rate_limit.return_value = RateLimitDecision(
        allowed=True,
        limit=60,
        remaining=54,
        reset_seconds=42,
        retry_after_seconds=0,
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/rate-limited")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["x-ratelimit-limit"] == "60"
        assert response.headers["x-ratelimit-remaining"] == "54"
        assert response.headers["x-ratelimit-reset"] == "42"
        assert "retry-after" not in response.headers


async def test_enforce_rate_limit_exceeded_raises_429(test_app, mock_limiter):
    """Verify exhausted quota raises 429 Too Many Requests with Retry-After header."""
    mock_limiter.check_rate_limit.return_value = RateLimitDecision(
        allowed=False,
        limit=60,
        remaining=0,
        reset_seconds=15,
        retry_after_seconds=15,
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/rate-limited")

        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert response.headers["retry-after"] == "15"
        assert response.headers["x-ratelimit-limit"] == "60"
        assert response.headers["x-ratelimit-remaining"] == "0"
        assert response.headers["x-ratelimit-reset"] == "15"


def test_get_rate_limiter_factory():
    """Verify factory returns configured SlidingWindowLimiter instance."""
    limiter = get_rate_limiter()
    assert isinstance(limiter, SlidingWindowLimiter)
