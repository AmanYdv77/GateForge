from fastapi import APIRouter, Depends, status

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.schemas.quota import QuotaUtilization
from gateforge.services.quota_monitor import QuotaMonitorService

router = APIRouter(prefix="/quota", tags=["Quota Monitoring"])


def get_quota_monitor_service() -> QuotaMonitorService:
    """Dependency provider for QuotaMonitorService."""
    return QuotaMonitorService()


@router.get(
    "/status",
    response_model=QuotaUtilization,
    status_code=status.HTTP_200_OK,
    summary="Inspect Real-Time Quota Consumption",
    description="Retrieve live sliding-window quota usage, percentage capacity, and threshold alert flags.",
)
async def get_quota_status(
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    monitor: QuotaMonitorService = Depends(get_quota_monitor_service),
) -> QuotaUtilization:
    """Evaluate caller quota consumption and return threshold alerts."""
    return await monitor.get_key_utilization(
        key_id=auth_key.key_id,
        limit_rpm=auth_key.rate_limit_rpm,
    )
