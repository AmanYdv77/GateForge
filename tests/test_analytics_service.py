from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateforge.models.api_key import APIKey
from gateforge.models.base import Base
from gateforge.models.usage import HourlyUsageRollup, UsageRecord
from gateforge.models.user import User
from gateforge.schemas.analytics import AnalyticsOverview, TimeSeriesPoint
from gateforge.services.analytics import UsageAnalyticsService


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
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


@pytest.mark.asyncio
async def test_analytics_overview_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify empty database returns clean zeroed overview."""
    async with session_factory() as session:
        overview = await UsageAnalyticsService.get_overview(session)
        assert isinstance(overview, AnalyticsOverview)
        assert overview.total_requests == 0
        assert overview.successful_requests == 0
        assert overview.client_error_requests == 0
        assert overview.rate_limited_requests == 0
        assert overview.server_error_requests == 0
        assert overview.avg_latency_ms == 0.0
        assert overview.p95_latency_ms == 0.0
        assert overview.p99_latency_ms == 0.0


@pytest.mark.asyncio
async def test_analytics_overview_calculation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify metric categorization and latency percentile computations."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email=f"analytics_{uuid4().hex[:8]}@example.com",
            hashed_password="hashed_pw",
            tier="pro",
        )
        session.add(user)
        await session.flush()

        key = APIKey(
            id=uuid4(),
            user_id=user.id,
            name="Analytics Test Key",
            key_prefix="gfg_live_ana",
            key_suffix="1234",
            key_hash=f"hash_{uuid4().hex}",
            scopes=["read:data"],
            is_active=True,
        )
        session.add(key)
        await session.flush()

        now = datetime.now(UTC)

        # Seed 10 records with known statuses and latencies
        statuses_latencies = [
            (200, 1.0),
            (200, 2.0),
            (201, 3.0),
            (204, 4.0),
            (400, 5.0),
            (403, 6.0),
            (429, 7.0),
            (429, 8.0),
            (500, 9.0),
            (503, 10.0),
        ]

        for status_code, latency in statuses_latencies:
            record = UsageRecord(
                id=uuid4(),
                request_id=f"req-{uuid4().hex[:6]}",
                key_id=key.id,
                user_id=user.id,
                method="POST",
                path="/api/v1/gateway/echo",
                status_code=status_code,
                latency_ms=latency,
                timestamp=now - timedelta(minutes=5),
            )
            session.add(record)

        await session.commit()

        overview = await UsageAnalyticsService.get_overview(
            session=session,
            key_id=key.id,
            user_id=user.id,
        )

        assert overview.total_requests == 10
        assert overview.successful_requests == 4  # 200, 200, 201, 204
        assert overview.client_error_requests == 2  # 400, 403 (excludes 429)
        assert overview.rate_limited_requests == 2  # 429, 429
        assert overview.server_error_requests == 2  # 500, 503
        assert overview.avg_latency_ms == 5.5  # sum 55 / 10 = 5.5
        assert overview.p95_latency_ms >= 9.0
        assert overview.p99_latency_ms >= 9.0


@pytest.mark.asyncio
async def test_analytics_hourly_rollups(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify fetching ordered time-series rollup data points."""
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            email=f"analytics_{uuid4().hex[:8]}@example.com",
            hashed_password="hashed_pw",
            tier="pro",
        )
        session.add(user)
        await session.flush()

        key = APIKey(
            id=uuid4(),
            user_id=user.id,
            name="Rollup Key",
            key_prefix="gfg_live_rol",
            key_suffix="5678",
            key_hash=f"hash_{uuid4().hex}",
            scopes=["read:data"],
            is_active=True,
        )
        session.add(key)
        await session.flush()

        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

        for i in range(3):
            rollup = HourlyUsageRollup(
                id=uuid4(),
                key_id=key.id,
                bucket_hour=now - timedelta(hours=3 - i),
                total_requests=100 * (i + 1),
                success_requests=90 * (i + 1),
                client_error_requests=5 * (i + 1),
                rate_limited_requests=3 * (i + 1),
                server_error_requests=2 * (i + 1),
                avg_latency_ms=2.0 + i,
                p95_latency_ms=5.0 + i,
                p99_latency_ms=8.0 + i,
            )
            session.add(rollup)

        await session.commit()

        points = await UsageAnalyticsService.get_hourly_rollups(session, key_id=key.id)
        assert len(points) == 3
        assert isinstance(points[0], TimeSeriesPoint)
        assert points[0].total_requests == 100
        assert points[1].total_requests == 200
        assert points[2].total_requests == 300
        assert points[0].rate_limited_requests == 3
