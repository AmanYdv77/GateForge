from unittest.mock import AsyncMock, MagicMock

from redis.exceptions import ConnectionError as RedisConnectionError

from gateforge.core.ratelimit import SLIDING_WINDOW_LUA, SlidingWindowLimiter
from gateforge.schemas.ratelimit import RateLimitDecision


def test_ratelimit_decision_schema():
    """Verify RateLimitDecision schema initializes with proper field constraints."""
    decision = RateLimitDecision(
        allowed=True,
        limit=100,
        remaining=99,
        reset_seconds=60,
        retry_after_seconds=0,
    )
    assert decision.allowed is True
    assert decision.limit == 100
    assert decision.remaining == 99
    assert decision.reset_seconds == 60
    assert decision.retry_after_seconds == 0


def test_lua_script_syntax_integrity():
    """Verify essential atomic sliding-window Redis commands are present in Lua source."""
    assert "ZREMRANGEBYSCORE" in SLIDING_WINDOW_LUA
    assert "ZCARD" in SLIDING_WINDOW_LUA
    assert "ZADD" in SLIDING_WINDOW_LUA
    assert "EXPIRE" in SLIDING_WINDOW_LUA
    assert "ZRANGE" in SLIDING_WINDOW_LUA


async def test_check_rate_limit_allowed():
    """Verify check_rate_limit correctly parses Lua allow response."""
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=[1, 60, 45, 60, 0])

    limiter = SlidingWindowLimiter(redis_client=mock_redis)
    decision = await limiter.check_rate_limit(
        identifier="client_abc",
        limit=60,
        window_seconds=60,
    )

    assert decision.allowed is True
    assert decision.limit == 60
    assert decision.remaining == 45
    assert decision.reset_seconds == 60
    assert decision.retry_after_seconds == 0
    mock_redis.eval.assert_awaited_once()


async def test_check_rate_limit_blocked():
    """Verify check_rate_limit correctly parses Lua blocked/throttled response."""
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=[0, 60, 0, 18, 18])

    limiter = SlidingWindowLimiter(redis_client=mock_redis)
    decision = await limiter.check_rate_limit(
        identifier="client_exceeded",
        limit=60,
        window_seconds=60,
    )

    assert decision.allowed is False
    assert decision.limit == 60
    assert decision.remaining == 0
    assert decision.reset_seconds == 18
    assert decision.retry_after_seconds == 18


async def test_check_rate_limit_fail_open_on_redis_error():
    """Verify fail-open behavior: when Redis experiences outage, traffic is allowed."""
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(side_effect=RedisConnectionError("Redis cluster unreachable"))

    limiter = SlidingWindowLimiter(redis_client=mock_redis)
    decision = await limiter.check_rate_limit(
        identifier="client_fallback",
        limit=100,
        window_seconds=60,
    )

    assert decision.allowed is True
    assert decision.limit == 100
    assert decision.remaining == 1
    assert decision.retry_after_seconds == 0
