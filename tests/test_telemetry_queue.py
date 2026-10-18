from uuid import uuid4

from gateforge.core.telemetry_queue import TelemetryQueue, get_telemetry_queue
from gateforge.schemas.telemetry import RequestTelemetry


def test_request_telemetry_schema() -> None:
    """Verify RequestTelemetry schema fields and default timestamp."""
    key_id = uuid4()
    user_id = uuid4()

    event = RequestTelemetry(
        request_id="req-test-123",
        key_id=key_id,
        user_id=user_id,
        method="GET",
        path="/api/v1/gateway/verify",
        status_code=200,
        latency_ms=1.45,
        client_ip="192.168.1.1",
    )

    assert event.request_id == "req-test-123"
    assert event.key_id == key_id
    assert event.user_id == user_id
    assert event.latency_ms == 1.45
    assert event.status_code == 200
    assert event.timestamp is not None


def test_telemetry_queue_enqueue_and_drain() -> None:
    """Verify items can be non-blockingly buffered and batch drained."""
    queue = TelemetryQueue(maxsize=100)

    for i in range(10):
        item = RequestTelemetry(
            request_id=f"req-{i}",
            method="POST",
            path="/api/v1/gateway/echo",
            status_code=200,
            latency_ms=float(i),
        )
        enqueued = queue.enqueue_nowait(item)
        assert enqueued is True

    assert queue.qsize == 10

    # Drain partial batch of 6 items
    batch1 = queue.drain_batch(max_items=6)
    assert len(batch1) == 6
    assert batch1[0].request_id == "req-0"
    assert batch1[5].request_id == "req-5"
    assert queue.qsize == 4

    # Drain remaining
    batch2 = queue.drain_batch(max_items=10)
    assert len(batch2) == 4
    assert queue.qsize == 0


def test_telemetry_queue_backpressure_drop() -> None:
    """Verify queue drops events safely when saturated instead of blocking or crashing."""
    small_queue = TelemetryQueue(maxsize=2)

    item1 = RequestTelemetry(request_id="1", method="GET", path="/", status_code=200, latency_ms=1)
    item2 = RequestTelemetry(request_id="2", method="GET", path="/", status_code=200, latency_ms=1)
    item3 = RequestTelemetry(request_id="3", method="GET", path="/", status_code=200, latency_ms=1)

    assert small_queue.enqueue_nowait(item1) is True
    assert small_queue.enqueue_nowait(item2) is True
    # 3rd item exceeds capacity
    assert small_queue.enqueue_nowait(item3) is False
    assert small_queue.dropped_count == 1
    assert small_queue.qsize == 2


def test_get_telemetry_queue_singleton() -> None:
    """Verify get_telemetry_queue provides cached singleton instance."""
    q1 = get_telemetry_queue()
    q2 = get_telemetry_queue()
    assert q1 is q2
    assert isinstance(q1, TelemetryQueue)
