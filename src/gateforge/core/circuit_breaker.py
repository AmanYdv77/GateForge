import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(StrEnum):
    """Possible operational states of the resilient circuit breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is rejected because the circuit breaker is OPEN."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN; failing fast. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """Thread-safe and async-native circuit breaker preventing cascading backend service outages."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.1, recovery_timeout)
        self.half_open_success_threshold = max(1, half_open_success_threshold)

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._opened_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current operational state, automatically checking recovery timeout expiration."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        """Current consecutive failures recorded."""
        return self._failure_count

    async def _check_and_update_state(self) -> None:
        """Transition from OPEN to HALF_OPEN if timeout has elapsed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(
                    "circuit_breaker_half_open",
                    breaker=self.name,
                    elapsed_seconds=round(elapsed, 2),
                )
            else:
                remaining = self.recovery_timeout - elapsed
                raise CircuitBreakerOpenError(self.name, retry_after=remaining)

    async def record_success(self) -> None:
        """Record successful call outcome, closing circuit if recovery threshold met."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("circuit_breaker_closed", breaker=self.name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self, exc: Exception | None = None) -> None:
        """Record call failure, tripping circuit to OPEN if threshold reached."""
        async with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._success_count = 0
                logger.warning(
                    "circuit_breaker_tripped_open",
                    breaker=self.name,
                    consecutive_failures=self._failure_count,
                    reason=str(exc) if exc else None,
                )

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute async function guarded by circuit breaker state machine."""
        async with self._lock:
            await self._check_and_update_state()

        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            await self.record_failure(exc)
            raise

    def reset(self) -> None:
        """Explicitly reset circuit breaker to pristine CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = 0.0
