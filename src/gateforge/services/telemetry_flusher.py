import asyncio
import contextlib
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateforge.core.database import async_session_factory
from gateforge.core.telemetry_queue import TelemetryQueue, get_telemetry_queue
from gateforge.models.usage import UsageRecord
from gateforge.schemas.telemetry import RequestTelemetry

logger = structlog.get_logger(__name__)


class TelemetryFlusherService:
    """High-throughput background batch flusher draining buffered telemetry into PostgreSQL."""

    def __init__(
        self,
        queue: TelemetryQueue | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        batch_size: int = 50,
        interval_seconds: float = 2.0,
    ) -> None:
        self.queue: TelemetryQueue = queue or get_telemetry_queue()
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory or async_session_factory
        self.batch_size: int = batch_size
        self.interval_seconds: float = interval_seconds
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._total_flushed: int = 0

    @property
    def total_flushed(self) -> int:
        """Total count of telemetry records persisted to PostgreSQL."""
        return self._total_flushed

    async def flush_batch(self, session: AsyncSession, batch: list[RequestTelemetry]) -> int:
        """Persist a discrete list of telemetry items into usage_records within a single transaction."""
        if not batch:
            return 0

        records = [
            UsageRecord(
                id=uuid4(),
                request_id=item.request_id,
                key_id=item.key_id,
                user_id=item.user_id,
                method=item.method,
                path=item.path,
                status_code=item.status_code,
                latency_ms=item.latency_ms,
                client_ip=item.client_ip,
                timestamp=item.timestamp,
            )
            for item in batch
        ]

        session.add_all(records)
        await session.commit()
        self._total_flushed += len(records)
        logger.debug("telemetry_batch_flushed", count=len(records), total_flushed=self._total_flushed)
        return len(records)

    async def flush_pending(self) -> int:
        """Drain up to batch_size records from queue and flush to database."""
        batch = self.queue.drain_batch(max_items=self.batch_size)
        if not batch:
            return 0

        try:
            async with self.session_factory() as session:
                return await self.flush_batch(session, batch)
        except Exception as exc:
            logger.error(
                "telemetry_flusher_db_error",
                error=str(exc),
                dropped_batch_size=len(batch),
            )
            return 0

    async def _worker_loop(self) -> None:
        """Continuous background execution loop."""
        while self._running:
            try:
                flushed = await self.flush_pending()
                if flushed == 0:
                    await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("telemetry_flusher_unexpected_error", error=str(exc))
                await asyncio.sleep(self.interval_seconds)

    def start(self) -> None:
        """Start the background worker task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._worker_loop())
            logger.info("telemetry_flusher_started", batch_size=self.batch_size)

    async def stop(self) -> None:
        """Gracefully stop background worker and drain remaining items."""
        if self._running:
            self._running = False
            if self._task is not None:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            # Final drain of any items remaining in memory
            while self.queue.qsize > 0:
                await self.flush_pending()
            logger.info("telemetry_flusher_stopped", total_flushed=self._total_flushed)
