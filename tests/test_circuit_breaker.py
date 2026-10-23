import asyncio

import pytest

from gateforge.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed() -> None:
    """Verify circuit breaker initializes in CLOSED state with zero failures."""
    cb = CircuitBreaker("test_breaker", failure_threshold=3, recovery_timeout=0.2)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0

    async def success_op() -> str:
        return "ok"

    res = await cb.call(success_op)
    assert res == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_trips_to_open() -> None:
    """Verify consecutive failures trip breaker to OPEN, failing fast without executing target."""
    cb = CircuitBreaker("redis_breaker", failure_threshold=2, recovery_timeout=0.2)
    call_count = 0

    async def failing_op() -> None:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("Redis socket timeout")

    # 1st failure
    with pytest.raises(ConnectionError):
        await cb.call(failing_op)
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1
    assert call_count == 1

    # 2nd failure -> trips OPEN
    with pytest.raises(ConnectionError):
        await cb.call(failing_op)
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 2
    assert call_count == 2

    # 3rd attempt: fails fast with CircuitBreakerOpenError without calling failing_op
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await cb.call(failing_op)
    assert exc_info.value.name == "redis_breaker"
    assert exc_info.value.retry_after > 0
    assert call_count == 2  # Not invoked


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_to_closed() -> None:
    """Verify breaker transitions OPEN -> HALF_OPEN -> CLOSED on successful trial calls."""
    cb = CircuitBreaker(
        "db_breaker",
        failure_threshold=1,
        recovery_timeout=0.1,
        half_open_success_threshold=2,
    )

    async def flaky_op(should_succeed: bool) -> str:
        if not should_succeed:
            raise RuntimeError("Database pool saturated")
        return "healthy"

    # Trip to OPEN
    with pytest.raises(RuntimeError):
        await cb.call(flaky_op, False)
    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.12)
    assert cb.state == CircuitState.HALF_OPEN

    # 1st success in HALF_OPEN
    res1 = await cb.call(flaky_op, True)
    assert res1 == "healthy"

    # 2nd success in HALF_OPEN -> closes breaker
    res2 = await cb.call(flaky_op, True)
    assert res2 == "healthy"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens() -> None:
    """Verify a single failure during HALF_OPEN immediately re-trips the breaker to OPEN."""
    cb = CircuitBreaker("service_breaker", failure_threshold=1, recovery_timeout=0.1)

    async def fail() -> None:
        raise ValueError("Service error")

    # Trip to OPEN
    with pytest.raises(ValueError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN

    # Wait for HALF_OPEN
    await asyncio.sleep(0.12)
    assert cb.state == CircuitState.HALF_OPEN

    # Failure in HALF_OPEN trips immediately back to OPEN
    with pytest.raises(ValueError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_explicit_reset() -> None:
    """Verify explicit reset resets state and counters."""
    cb = CircuitBreaker("manual_breaker", failure_threshold=1)
    cb._state = CircuitState.OPEN
    cb._failure_count = 5
    cb._success_count = 2

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
