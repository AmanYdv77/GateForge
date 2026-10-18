from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateforge.core.telemetry_queue import get_telemetry_queue
from gateforge.main import create_app
from gateforge.models.base import Base
from gateforge.models.usage import UsageRecord
from gateforge.schemas.cache import CachedKeyData
from gateforge.schemas.ratelimit import RateLimitDecision
from gateforge.services.analytics import UsageAnalyticsService
from gateforge.services.telemetry_flusher import TelemetryFlusherService


@pytest.fixture
async def e2e_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await test_engine.dispose()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.mark.asyncio
async def test_telemetry_full_e2e_pipeline(
    app: FastAPI,
    e2e_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify complete telemetry lifecycle: Gateway Request -> Middleware -> Queue -> Batch Flusher -> DB -> Analytics."""
    queue = get_telemetry_queue()
    queue.clear()

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

        # 1. Dispatch gateway request through HTTP client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {
                "X-API-Key": "gfg_live_abcdef12345678901234567890123456",
                "x-request-id": "e2e-trace-999",
            }
            res = await client.post(
                "/api/v1/gateway/echo",
                json={"payload": {"test": "e2e_data"}},
                headers=headers,
            )
            assert res.status_code == 200
            assert res.headers["x-request-id"] == "e2e-trace-999"

        # 2. Verify queue received telemetry asynchronously without blocking client
        assert queue.qsize == 1

        # 3. Drain and flush into database via TelemetryFlusherService
        flusher = TelemetryFlusherService(queue=queue, session_factory=e2e_session_factory)
        flushed_count = await flusher.flush_pending()
        assert flushed_count == 1
        assert queue.qsize == 0

        # 4. Verify database persistence
        async with e2e_session_factory() as session:
            query = select(UsageRecord).where(UsageRecord.request_id == "e2e-trace-999")
            result = await session.execute(query)
            record = result.scalar_one_or_none()
            assert record is not None
            assert record.key_id == key_id
            assert record.user_id == user_id
            assert record.status_code == 200
            assert record.path == "/api/v1/gateway/echo"
            assert record.method == "POST"
            assert record.latency_ms >= 0.0

            # 5. Verify analytics aggregation queries over persisted telemetry
            overview = await UsageAnalyticsService.get_overview(session, key_id=key_id)
            assert overview.total_requests == 1
            assert overview.successful_requests == 1
            assert overview.client_error_requests == 0


@pytest.mark.asyncio
async def test_telemetry_unauthorized_request_e2e(
    app: FastAPI,
    e2e_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify unauthorized gateway requests (401) are tracked and aggregated properly."""
    queue = get_telemetry_queue()
    queue.clear()

    with patch(
        "gateforge.api.dependencies.auth.AuthCacheService.get_cached_key",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {"x-request-id": "e2e-unauth-401"}
            res = await client.get("/api/v1/gateway/verify", headers=headers)
            assert res.status_code == 401

        assert queue.qsize == 1

        flusher = TelemetryFlusherService(queue=queue, session_factory=e2e_session_factory)
        await flusher.flush_pending()

        async with e2e_session_factory() as session:
            query = select(UsageRecord).where(UsageRecord.request_id == "e2e-unauth-401")
            result = await session.execute(query)
            record = result.scalar_one_or_none()
            assert record is not None
            assert record.key_id is None
            assert record.status_code == 401

            overview = await UsageAnalyticsService.get_overview(session)
            assert overview.total_requests == 1
            assert overview.successful_requests == 0
            assert overview.client_error_requests == 1
