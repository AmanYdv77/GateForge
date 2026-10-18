import time
from uuid import uuid4

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from gateforge.core.redis import get_redis_client
from gateforge.schemas.ratelimit import RateLimitDecision

logger = structlog.get_logger(__name__)

SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now_ms - window_ms

-- 1. Evict elements older than the sliding window boundary
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- 2. Count current elements inside active window
local current_requests = redis.call('ZCARD', key)

-- 3. Evaluate quota
if current_requests < limit then
    redis.call('ZADD', key, now_ms, member)
    local ttl_seconds = math.ceil(window_ms / 1000) + 2
    redis.call('EXPIRE', key, ttl_seconds)

    local remaining = limit - current_requests - 1
    local reset_seconds = math.ceil(window_ms / 1000)
    return {1, limit, remaining, reset_seconds, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_time = now_ms
    if #oldest >= 2 then
        oldest_time = tonumber(oldest[2])
    end

    local time_until_oldest_expires = (oldest_time + window_ms) - now_ms
    if time_until_oldest_expires < 0 then
        time_until_oldest_expires = 0
    end
    local retry_after = math.max(1, math.ceil(time_until_oldest_expires / 1000))
    local reset_seconds = retry_after

    return {0, limit, 0, reset_seconds, retry_after}
end
"""


class SlidingWindowLimiter:
    """Atomic sliding-window rate limiter executed directly on Redis single-threaded engine."""

    def __init__(self, redis_client: Redis | None = None) -> None:
        self._client: Redis = redis_client or get_redis_client()
        self._script: str = SLIDING_WINDOW_LUA

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitDecision:
        """Evaluate rate limit using atomic Redis Lua sliding window.

        Args:
            identifier: Unique rate limit bucket key (e.g. key UUID or IP address).
            limit: Maximum requests allowed in the sliding window.
            window_seconds: Duration of the sliding window in seconds.

        Returns:
            RateLimitDecision: Quota judgment with remaining tokens and reset intervals.
        """
        redis_key = f"ratelimit:{identifier}"
        now_ms = int(time.time() * 1000)
        window_ms = window_seconds * 1000
        member_id = f"{now_ms}:{uuid4().hex[:8]}"

        try:
            raw_result = await self._client.eval(
                self._script,
                1,
                redis_key,
                str(now_ms),
                str(window_ms),
                str(limit),
                member_id,
            )

            # Lua returns array: {allowed_flag, limit, remaining, reset_seconds, retry_after}
            allowed = bool(raw_result[0] == 1)
            eval_limit = int(raw_result[1])
            remaining = int(raw_result[2])
            reset_seconds = int(raw_result[3])
            retry_after = int(raw_result[4])

            return RateLimitDecision(
                allowed=allowed,
                limit=eval_limit,
                remaining=remaining,
                reset_seconds=reset_seconds,
                retry_after_seconds=retry_after,
            )

        except (RedisError, OSError) as exc:
            logger.warning(
                "rate_limiter_redis_degraded_fail_open",
                identifier=identifier,
                error=str(exc),
            )
            # Fail-open design: downstream services remain available during Redis degradations
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=1,
                reset_seconds=window_seconds,
                retry_after_seconds=0,
            )
