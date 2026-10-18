from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.core.database import get_db_session
from gateforge.schemas.analytics import AnalyticsOverview, AnalyticsTimeSeriesResponse
from gateforge.services.analytics import UsageAnalyticsService

router = APIRouter(prefix="/analytics", tags=["Developer Analytics"])


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    status_code=status.HTTP_200_OK,
    summary="Get Usage & Latency Overview",
    description="Retrieve high-level volume, success rate, and p95/p99 latency percentiles for the caller.",
)
async def get_analytics_overview(
    since_hours: int = Query(default=24, ge=1, le=720, description="Rolling inspection window in hours"),
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db_session),
) -> AnalyticsOverview:
    """Calculate caller analytics overview over rolling duration."""
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    return await UsageAnalyticsService.get_overview(
        session=db,
        key_id=auth_key.key_id,
        user_id=auth_key.user_id,
        since=since,
    )


@router.get(
    "/time-series",
    response_model=AnalyticsTimeSeriesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Hourly Time-Series Metrics",
    description="Retrieve ordered hourly bucket metrics for rendering developer dashboard charts.",
)
async def get_time_series_metrics(
    since_days: int = Query(default=7, ge=1, le=30, description="Rolling time series duration in days"),
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db_session),
) -> AnalyticsTimeSeriesResponse:
    """Retrieve pre-aggregated hourly time-series rollup data points."""
    since = datetime.now(UTC) - timedelta(days=since_days)
    points = await UsageAnalyticsService.get_hourly_rollups(
        session=db,
        key_id=auth_key.key_id,
        since=since,
    )
    return AnalyticsTimeSeriesResponse(points=points)
