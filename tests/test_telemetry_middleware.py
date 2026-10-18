from collections.abc import Generator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gateforge.core.telemetry_queue import get_telemetry_queue
from gateforge.main import create_app
from gateforge.schemas.cache import CachedKeyData
from gateforge.schemas.ratelimit import RateLimitDecision


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture(autouse=True)
def clear_queue() -> Generator[None, None, None]:
    queue = get_telemetry_queue()
    queue.clear()
    yield
    queue.clear()


@pytest.mark.asyncio
async def test_telemetry_middleware_injects_headers(app: FastAPI) -> None:
    """Verify X-Request-ID and X-Response-Time headers are injected into response."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Without custom request ID
        res = await client.get("/health/live")
        assert res.status_code == 200
        assert "x-request-id" in res.headers
        assert "x-response-time" in res.headers
        assert res.headers["x-response-time"].endswith("ms")

        # 2. With client-supplied request ID
        custom_id = "req-client-custom-999"
        res_custom = await client.get("/health/live", headers={"x-request-id": custom_id})
        assert res_custom.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_telemetry_middleware_skips_excluded_health_paths(app: FastAPI) -> None:
    """Verify health and docs endpoints do not generate telemetry queue items."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/health/live")
        assert res.status_code == 200

        queue = get_telemetry_queue()
        assert queue.qsize == 0


@pytest.mark.asyncio
async def test_telemetry_middleware_captures_api_telemetry(app: FastAPI) -> None:
    """Verify standard API requests enqueue telemetry records."""
    key_id = uuid4()
    user_id = uuid4()
    cached_key = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:data"],
        rate_limit_rpm=60,
    )

    with (
        patch(
            "gateforge.api.dependencies.auth.AuthCacheService.get_cached_key",
            new_callable=AsyncMock,
            return_value=cached_key,
        ),
        patch(
            "gateforge.core.ratelimit.SlidingWindowLimiter.check_rate_limit",
            new_callable=AsyncMock,
        ) as mock_rl,
    ):
        mock_rl.return_value = RateLimitDecision(
            allowed=True,
            limit=60,
            remaining=59,
            reset_seconds=60,
            retry_after_seconds=0,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {
                "X-API-Key": "gfg_live_abcdef12345678901234567890123456",
                "x-request-id": "trace-corr-1",
            }
            res = await client.get("/api/v1/gateway/verify", headers=headers)
            assert res.status_code == 200

            queue = get_telemetry_queue()
            assert queue.qsize == 1

            batch = queue.drain_batch(max_items=10)
            assert len(batch) == 1
            item = batch[0]
            assert item.request_id == "trace-corr-1"
            assert item.key_id == key_id
            assert item.user_id == user_id
            assert item.path == "/api/v1/gateway/verify"
            assert item.method == "GET"
            assert item.status_code == 200
            assert item.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_telemetry_middleware_captures_unauthenticated_requests(app: FastAPI) -> None:
    """Verify unauthorized or invalid requests still record latency and status code."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/api/v1/gateway/verify")
        assert res.status_code == 401

        queue = get_telemetry_queue()
        assert queue.qsize == 1

        batch = queue.drain_batch(max_items=10)
        assert len(batch) == 1
        item = batch[0]
        assert item.key_id is None
        assert item.user_id is None
        assert item.status_code == 401
        assert item.path == "/api/v1/gateway/verify"
