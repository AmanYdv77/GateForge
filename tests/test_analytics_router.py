from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gateforge.main import create_app
from gateforge.schemas.analytics import AnalyticsOverview, TimeSeriesPoint
from gateforge.schemas.cache import CachedKeyData


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def sample_key_id() -> str:
    return str(uuid4())


@pytest.fixture
def sample_user_id() -> str:
    return str(uuid4())


@pytest.mark.asyncio
async def test_analytics_overview_unauthorized(app: FastAPI) -> None:
    """Verify endpoint rejects requests missing X-API-Key with 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/api/v1/analytics/overview")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_analytics_overview_authorized(app: FastAPI) -> None:
    """Verify authenticated caller retrieves structured analytics overview."""
    key_id = uuid4()
    user_id = uuid4()
    cached_key = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:analytics"],
        rate_limit_rpm=60,
    )

    mock_overview = AnalyticsOverview(
        total_requests=150,
        successful_requests=145,
        client_error_requests=3,
        rate_limited_requests=1,
        server_error_requests=1,
        avg_latency_ms=1.75,
        p95_latency_ms=4.20,
        p99_latency_ms=8.50,
    )

    with (
        patch(
            "gateforge.api.dependencies.auth.AuthCacheService.get_cached_key",
            new_callable=AsyncMock,
            return_value=cached_key,
        ),
        patch(
            "gateforge.api.v1.analytics.UsageAnalyticsService.get_overview",
            new_callable=AsyncMock,
            return_value=mock_overview,
        ) as mock_get_overview,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {"X-API-Key": "gfg_live_abcdef12345678901234567890123456"}
            res = await client.get("/api/v1/analytics/overview?since_hours=48", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["total_requests"] == 150
            assert data["successful_requests"] == 145
            assert data["avg_latency_ms"] == 1.75
            mock_get_overview.assert_awaited_once()


@pytest.mark.asyncio
async def test_analytics_time_series_authorized(app: FastAPI) -> None:
    """Verify authenticated caller retrieves time-series rollups."""
    key_id = uuid4()
    user_id = uuid4()
    cached_key = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:analytics"],
        rate_limit_rpm=60,
    )

    mock_points = [
        TimeSeriesPoint(
            bucket_timestamp=datetime.now(UTC),
            total_requests=50,
            success_requests=48,
            error_requests=2,
            rate_limited_requests=0,
            avg_latency_ms=1.2,
        )
    ]

    with (
        patch(
            "gateforge.api.dependencies.auth.AuthCacheService.get_cached_key",
            new_callable=AsyncMock,
            return_value=cached_key,
        ),
        patch(
            "gateforge.api.v1.analytics.UsageAnalyticsService.get_hourly_rollups",
            new_callable=AsyncMock,
            return_value=mock_points,
        ) as mock_get_rollups,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {"X-API-Key": "gfg_live_abcdef12345678901234567890123456"}
            res = await client.get("/api/v1/analytics/time-series?since_days=14", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert len(data["points"]) == 1
            assert data["points"][0]["total_requests"] == 50
            mock_get_rollups.assert_awaited_once()
