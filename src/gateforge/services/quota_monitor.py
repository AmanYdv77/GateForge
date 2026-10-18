import time
from uuid import UUID

import structlog
from redis.asyncio import Redis

from gateforge.core.redis import get_redis_client
from gateforge.schemas.quota import QuotaUtilization

logger = structlog.get_logger(__name__)


class QuotaMonitorService:
    """Real-time quota inspection service computing tier consumption and threshold alerts."""

    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis: Redis = redis_client or get_redis_client()

    async def get_key_utilization(
        self,
        key_id: UUID,
        limit_rpm: int,
        tier: str = "free",
        window_seconds: int = 60,
    ) -> QuotaUtilization:
        """Inspect current sliding-window cardinality in Redis and evaluate threshold alarms."""
        key_name = f"ratelimit:{key_id}"
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (window_seconds * 1000)

        current_count = 0
        try:
            current_count = int(await self.redis.zcount(key_name, window_start_ms, "+inf"))
        except Exception as exc:
            logger.warning("quota_monitor_redis_degraded", key_id=str(key_id), error=str(exc))
            current_count = 0

        percent = round((current_count / max(limit_rpm, 1)) * 100, 1)

        warning_threshold: str | None = None
        is_throttled = False

        if percent >= 100.0:
            warning_threshold = "EXHAUSTED_100"
            is_throttled = True
        elif percent >= 95.0:
            warning_threshold = "CRITICAL_95"
        elif percent >= 80.0:
            warning_threshold = "WARNING_80"

        return QuotaUtilization(
            key_id=key_id,
            tier=tier,
            rpm_limit=limit_rpm,
            current_usage=current_count,
            utilization_percent=percent,
            warning_threshold=warning_threshold,
            is_throttled=is_throttled,
        )
