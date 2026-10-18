from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from gateforge.main import create_app
from gateforge.schemas.cache import CachedKeyData
from gateforge.schemas.quota import QuotaUtilization
from gateforge.services.quota_monitor import QuotaMonitorService


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock(spec=Redis)
    redis.zcount = AsyncMock()
    return redis


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.mark.asyncio
async def test_quota_monitor_normal_utilization(mock_redis: AsyncMock) -> None:
    """Verify healthy utilization under 80% emits no alarm thresholds."""
    mock_redis.zcount.return_value = 35
    service = QuotaMonitorService(redis_client=mock_redis)

    key_id = uuid4()
    status = await service.get_key_utilization(key_id=key_id, limit_rpm=100)

    assert status.key_id == key_id
    assert status.current_usage == 35
    assert status.utilization_percent == 35.0
    assert status.warning_threshold is None
    assert status.is_throttled is False


@pytest.mark.asyncio
async def test_quota_monitor_warning_80(mock_redis: AsyncMock) -> None:
    """Verify usage between 80% and 94% triggers WARNING_80 alert."""
    mock_redis.zcount.return_value = 85
    service = QuotaMonitorService(redis_client=mock_redis)

    status = await service.get_key_utilization(key_id=uuid4(), limit_rpm=100)
    assert status.utilization_percent == 85.0
    assert status.warning_threshold == "WARNING_80"
    assert status.is_throttled is False


@pytest.mark.asyncio
async def test_quota_monitor_critical_95(mock_redis: AsyncMock) -> None:
    """Verify usage between 95% and 99% triggers CRITICAL_95 alert."""
    mock_redis.zcount.return_value = 96
    service = QuotaMonitorService(redis_client=mock_redis)

    status = await service.get_key_utilization(key_id=uuid4(), limit_rpm=100)
    assert status.utilization_percent == 96.0
    assert status.warning_threshold == "CRITICAL_95"
    assert status.is_throttled is False


@pytest.mark.asyncio
async def test_quota_monitor_exhausted_100(mock_redis: AsyncMock) -> None:
    """Verify usage at or above 100% triggers EXHAUSTED_100 and throttled flag."""
    mock_redis.zcount.return_value = 100
    service = QuotaMonitorService(redis_client=mock_redis)

    status = await service.get_key_utilization(key_id=uuid4(), limit_rpm=100)
    assert status.utilization_percent == 100.0
    assert status.warning_threshold == "EXHAUSTED_100"
    assert status.is_throttled is True


@pytest.mark.asyncio
async def test_quota_router_status_endpoint(app: FastAPI) -> None:
    """Verify authenticated caller accesses real-time quota status endpoint."""
    key_id = uuid4()
    cached_key = CachedKeyData(
        key_id=key_id,
        user_id=uuid4(),
        is_active=True,
        scopes=["read:quota"],
        rate_limit_rpm=100,
    )

    with (
        patch(
            "gateforge.api.dependencies.auth.AuthCacheService.get_cached_key",
            new_callable=AsyncMock,
            return_value=cached_key,
        ),
        patch(
            "gateforge.services.quota_monitor.QuotaMonitorService.get_key_utilization",
            new_callable=AsyncMock,
        ) as mock_get_util,
    ):
        mock_get_util.return_value = QuotaUtilization(
            key_id=key_id,
            tier="pro",
            rpm_limit=100,
            current_usage=45,
            utilization_percent=45.0,
            warning_threshold=None,
            is_throttled=False,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {"X-API-Key": "gfg_live_abcdef12345678901234567890123456"}
            res = await client.get("/api/v1/quota/status", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["rpm_limit"] == 100
            assert data["current_usage"] == 45
            assert data["utilization_percent"] == 45.0
            assert data["is_throttled"] is False
