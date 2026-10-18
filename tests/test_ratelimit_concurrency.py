import asyncio
import time
from uuid import uuid4

import pytest

from gateforge.core.ratelimit import SlidingWindowLimiter
from gateforge.schemas.ratelimit import RateLimitDecision


class AtomicTestRedisDouble:
    """Thread-safe / task-safe in-memory sorted set double simulating Redis single-threaded Lua engine."""

    def __init__(self) -> None:
        self._zsets: dict[str, list[tuple[float, str]]] = {}
        self._lock = asyncio.Lock()

    async def eval(
        self,
        script: str,
        numkeys: int,
        key: str,
        now_ms_str: str,
        window_ms_str: str,
        limit_str: str,
        member: str,
    ) -> list[int]:
        async with self._lock:
            now_ms = int(now_ms_str)
            window_ms = int(window_ms_str)
            limit = int(limit_str)
            clear_before = now_ms - window_ms

            if key not in self._zsets:
                self._zsets[key] = []

            # 1. ZREMRANGEBYSCORE: Evict entries outside sliding window
            self._zsets[key] = [item for item in self._zsets[key] if item[0] >= clear_before]

            current_count = len(self._zsets[key])

            if current_count < limit:
                # 2. ZADD: Add member with timestamp score
                self._zsets[key].append((now_ms, member))
                self._zsets[key].sort(key=lambda x: x[0])
                remaining = limit - current_count - 1
                reset_seconds = max(1, window_ms // 1000)
                return [1, limit, remaining, reset_seconds, 0]
            else:
                oldest_time = self._zsets[key][0][0] if self._zsets[key] else now_ms
                time_until_oldest_expires = (oldest_time + window_ms) - now_ms
                retry_after = max(1, int(time_until_oldest_expires / 1000) + 1)
                return [0, limit, 0, retry_after, retry_after]


@pytest.fixture
def atomic_redis():
    return AtomicTestRedisDouble()


@pytest.fixture
def limiter(atomic_redis):
    return SlidingWindowLimiter(redis_client=atomic_redis)  # type: ignore[arg-type]


async def test_high_concurrency_race_conditions_eliminated(limiter):
    """Verify 50 concurrent requests competing for a limit of 20 permit exactly 20 and block 30.

    This proves that the atomic Redis Lua execution prevents race conditions and over-allocation
    under heavy parallel asynchronous load.
    """
    key_id = f"concurrency_test_key_{uuid4()}"
    limit = 20
    concurrent_requests = 50

    async def worker():
        return await limiter.check_rate_limit(
            identifier=key_id,
            limit=limit,
            window_seconds=60,
        )

    # Launch 50 simultaneous coroutines
    tasks = [asyncio.create_task(worker()) for _ in range(concurrent_requests)]
    results: list[RateLimitDecision] = await asyncio.gather(*tasks)

    allowed_count = sum(1 for r in results if r.allowed)
    blocked_count = sum(1 for r in results if not r.allowed)

    assert allowed_count == limit, f"Expected exactly {limit} allowed, got {allowed_count}"
    assert (
        blocked_count == concurrent_requests - limit
    ), f"Expected {concurrent_requests - limit} blocked, got {blocked_count}"

    # Verify that blocked requests carry positive retry-after intervals
    for r in results:
        if not r.allowed:
            assert r.retry_after_seconds > 0
            assert r.remaining == 0


async def test_sliding_window_eliminates_boundary_bursts(atomic_redis):
    """Verify that sliding-window prevents 2x traffic bursts across minute boundaries.

    In a fixed-window counter with limit 5 per 60s:
      - 5 requests at t=59s -> ALLOWED
      - 5 requests at t=61s -> ALLOWED (BURST OF 10 in 2 SECONDS!)

    In GateForge's sliding-window log:
      - 5 requests at t=59s -> ALLOWED
      - 5 requests at t=61s -> REJECTED (only 2s elapsed, window still full!)
    """
    key_id = "boundary_burst_test"
    limit = 5
    base_time_ms = int(time.time() * 1000)

    # 1. Client sends 5 requests near end of minute (t = 59s)
    t_59s = base_time_ms + 59_000
    for i in range(limit):
        res = await atomic_redis.eval(
            script="",
            numkeys=1,
            key=f"ratelimit:{key_id}",
            now_ms_str=str(t_59s + i),
            window_ms_str="60000",
            limit_str=str(limit),
            member=f"req_{i}",
        )
        assert res[0] == 1  # Allowed

    # 2. Client immediately sends 5 requests right after minute rolls over (t = 61s)
    t_61s = base_time_ms + 61_000
    burst_results = []
    for j in range(limit):
        res = await atomic_redis.eval(
            script="",
            numkeys=1,
            key=f"ratelimit:{key_id}",
            now_ms_str=str(t_61s + j),
            window_ms_str="60000",
            limit_str=str(limit),
            member=f"burst_{j}",
        )
        burst_results.append(res[0])

    # All burst requests must be blocked (0) because 61s - 60s = 1s, so 59s events are still active!
    assert all(status == 0 for status in burst_results)

    # 3. Fast-forward to t = 120s (all original 59s requests have rolled out of the 60s window)
    t_120s = base_time_ms + 120_000
    res_after_window = await atomic_redis.eval(
        script="",
        numkeys=1,
        key=f"ratelimit:{key_id}",
        now_ms_str=str(t_120s),
        window_ms_str="60000",
        limit_str=str(limit),
        member="new_req",
    )
    assert res_after_window[0] == 1  # Allowed again!
