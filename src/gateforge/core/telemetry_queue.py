import asyncio
from typing import Final

import structlog

from gateforge.schemas.telemetry import RequestTelemetry

logger = structlog.get_logger(__name__)

DEFAULT_QUEUE_CAPACITY: Final[int] = 10000


class TelemetryQueue:
    """Non-blocking bounded in-memory queue for high-throughput request telemetry ingestion."""

    def __init__(self, maxsize: int = DEFAULT_QUEUE_CAPACITY) -> None:
        self._queue: asyncio.Queue[RequestTelemetry] = asyncio.Queue(maxsize=maxsize)
        self._maxsize: int = maxsize
        self._dropped_count: int = 0

    @property
    def qsize(self) -> int:
        """Return current count of items buffered in the queue."""
        return self._queue.qsize()

    @property
    def dropped_count(self) -> int:
        """Total number of telemetry events dropped due to backpressure saturation."""
        return self._dropped_count

    def enqueue_nowait(self, item: RequestTelemetry) -> bool:
        """Enqueue telemetry event immediately without blocking active request worker.

        If queue is saturated, the event is dropped and counter incremented (fail-safe).
        """
        try:
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            self._dropped_count += 1
            if self._dropped_count % 100 == 1:
                logger.warning(
                    "telemetry_queue_backpressure_drop",
                    dropped_total=self._dropped_count,
                    capacity=self._maxsize,
                )
            return False

    def drain_batch(self, max_items: int = 50) -> list[RequestTelemetry]:
        """Drain up to `max_items` telemetry records from the queue synchronously."""
        batch: list[RequestTelemetry] = []
        while len(batch) < max_items and not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    def clear(self) -> None:
        """Clear all buffered items in queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


_telemetry_queue: TelemetryQueue | None = None


def get_telemetry_queue() -> TelemetryQueue:
    """Return singleton instance of TelemetryQueue."""
    global _telemetry_queue
    if _telemetry_queue is None:
        _telemetry_queue = TelemetryQueue()
    return _telemetry_queue
