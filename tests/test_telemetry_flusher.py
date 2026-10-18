from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateforge.core.telemetry_queue import TelemetryQueue
from gateforge.schemas.telemetry import RequestTelemetry
from gateforge.services.telemetry_flusher import TelemetryFlusherService


@pytest.fixture
def test_queue() -> TelemetryQueue:
    return TelemetryQueue(maxsize=100)


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add_all = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock) -> MagicMock:
    factory = MagicMock(spec=async_sessionmaker)
    factory.return_value.__aenter__.return_value = mock_session
    factory.return_value.__aexit__.return_value = None
    return factory


@pytest.mark.asyncio
async def test_flusher_flush_batch_persists_records(
    test_queue: TelemetryQueue, mock_session: AsyncMock
) -> None:
    """Verify flush_batch maps RequestTelemetry models to UsageRecord and calls commit."""
    flusher = TelemetryFlusherService(queue=test_queue)
    batch = [
        RequestTelemetry(
            request_id="req-1",
            key_id=uuid4(),
            user_id=uuid4(),
            method="GET",
            path="/api/v1/gateway/verify",
            status_code=200,
            latency_ms=1.5,
        ),
        RequestTelemetry(
            request_id="req-2",
            key_id=None,
            user_id=None,
            method="POST",
            path="/api/v1/keys",
            status_code=401,
            latency_ms=0.8,
        ),
    ]

    count = await flusher.flush_batch(mock_session, batch)
    assert count == 2
    assert flusher.total_flushed == 2
    mock_session.add_all.assert_called_once()
    records = mock_session.add_all.call_args[0][0]
    assert len(records) == 2
    assert records[0].request_id == "req-1"
    assert records[1].request_id == "req-2"
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_flusher_flush_pending_empty_queue(
    test_queue: TelemetryQueue, mock_session_factory: MagicMock
) -> None:
    """Verify flush_pending does nothing if queue is empty."""
    flusher = TelemetryFlusherService(queue=test_queue, session_factory=mock_session_factory)
    count = await flusher.flush_pending()
    assert count == 0
    mock_session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_flusher_flush_pending_with_items(
    test_queue: TelemetryQueue, mock_session_factory: MagicMock, mock_session: AsyncMock
) -> None:
    """Verify flush_pending drains queue and calls session."""
    flusher = TelemetryFlusherService(queue=test_queue, session_factory=mock_session_factory, batch_size=5)

    for i in range(3):
        test_queue.enqueue_nowait(
            RequestTelemetry(
                request_id=f"req-{i}",
                method="GET",
                path="/test",
                status_code=200,
                latency_ms=float(i),
            )
        )

    assert test_queue.qsize == 3
    count = await flusher.flush_pending()
    assert count == 3
    assert test_queue.qsize == 0
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_flusher_handles_db_exception_gracefully(
    test_queue: TelemetryQueue, mock_session_factory: MagicMock, mock_session: AsyncMock
) -> None:
    """Verify flusher catches DB errors without crashing."""
    mock_session.commit.side_effect = RuntimeError("DB connection dropped")
    flusher = TelemetryFlusherService(queue=test_queue, session_factory=mock_session_factory)

    test_queue.enqueue_nowait(
        RequestTelemetry(
            request_id="req-fail",
            method="GET",
            path="/fail",
            status_code=500,
            latency_ms=10.0,
        )
    )

    count = await flusher.flush_pending()
    assert count == 0
