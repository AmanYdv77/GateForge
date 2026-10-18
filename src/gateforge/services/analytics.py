from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.models.usage import HourlyUsageRollup, UsageRecord
from gateforge.schemas.analytics import AnalyticsOverview, TimeSeriesPoint

logger = structlog.get_logger(__name__)


class UsageAnalyticsService:
    """Service providing rolling analytics aggregations and time-series query processing."""

    @staticmethod
    async def get_overview(
        session: AsyncSession,
        key_id: UUID | None = None,
        user_id: UUID | None = None,
        since: datetime | None = None,
    ) -> AnalyticsOverview:
        """Calculate high-level summary overview metrics over specified window."""
        window_start = since or (datetime.now(UTC) - timedelta(days=1))

        query = select(
            func.count(UsageRecord.id).label("total"),
            func.count(UsageRecord.id).filter(UsageRecord.status_code < 400).label("success"),
            func.count(UsageRecord.id)
            .filter((UsageRecord.status_code >= 400) & (UsageRecord.status_code < 500) & (UsageRecord.status_code != 429))
            .label("client_error"),
            func.count(UsageRecord.id).filter(UsageRecord.status_code == 429).label("rate_limited"),
            func.count(UsageRecord.id).filter(UsageRecord.status_code >= 500).label("server_error"),
            func.coalesce(func.avg(UsageRecord.latency_ms), 0.0).label("avg_latency"),
        ).where(UsageRecord.timestamp >= window_start)

        if key_id is not None:
            query = query.where(UsageRecord.key_id == key_id)
        if user_id is not None:
            query = query.where(UsageRecord.user_id == user_id)

        result = await session.execute(query)
        row = result.one()

        # Compute percentiles from ordered latency records if records exist
        latencies_query = (
            select(UsageRecord.latency_ms)
            .where(UsageRecord.timestamp >= window_start)
            .order_by(UsageRecord.latency_ms.asc())
        )
        if key_id is not None:
            latencies_query = latencies_query.where(UsageRecord.key_id == key_id)
        if user_id is not None:
            latencies_query = latencies_query.where(UsageRecord.user_id == user_id)

        lat_result = await session.execute(latencies_query)
        latencies = [val for (val,) in lat_result.fetchall()]

        p95 = 0.0
        p99 = 0.0
        if latencies:
            p95_idx = int(len(latencies) * 0.95)
            p99_idx = int(len(latencies) * 0.99)
            p95 = round(float(latencies[min(p95_idx, len(latencies) - 1)]), 2)
            p99 = round(float(latencies[min(p99_idx, len(latencies) - 1)]), 2)

        return AnalyticsOverview(
            total_requests=int(row.total or 0),
            successful_requests=int(row.success or 0),
            client_error_requests=int(row.client_error or 0),
            rate_limited_requests=int(row.rate_limited or 0),
            server_error_requests=int(row.server_error or 0),
            avg_latency_ms=round(float(row.avg_latency or 0.0), 2),
            p95_latency_ms=p95,
            p99_latency_ms=p99,
        )

    @staticmethod
    async def get_hourly_rollups(
        session: AsyncSession,
        key_id: UUID,
        since: datetime | None = None,
    ) -> list[TimeSeriesPoint]:
        """Fetch pre-aggregated hourly rollup points for instant time-series charts."""
        window_start = since or (datetime.now(UTC) - timedelta(days=7))

        query = (
            select(HourlyUsageRollup)
            .where(
                (HourlyUsageRollup.key_id == key_id)
                & (HourlyUsageRollup.bucket_hour >= window_start)
            )
            .order_by(HourlyUsageRollup.bucket_hour.asc())
        )
        result = await session.execute(query)
        rollups = result.scalars().all()

        return [
            TimeSeriesPoint(
                bucket_timestamp=r.bucket_hour,
                total_requests=r.total_requests,
                success_requests=r.success_requests,
                error_requests=r.client_error_requests + r.server_error_requests,
                rate_limited_requests=r.rate_limited_requests,
                avg_latency_ms=round(r.avg_latency_ms, 2),
            )
            for r in rollups
        ]
