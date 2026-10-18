import uuid
from datetime import UTC, datetime

from gateforge.models.usage import HourlyUsageRollup, UsageRecord


def test_usage_record_model_attributes() -> None:
    """Verify UsageRecord field definitions and compound index definitions."""
    key_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    record = UsageRecord(
        request_id="req-12345",
        key_id=key_id,
        user_id=user_id,
        method="POST",
        path="/api/v1/gateway/echo",
        status_code=200,
        latency_ms=1.85,
        client_ip="10.0.0.1",
        timestamp=now,
    )

    assert record.request_id == "req-12345"
    assert record.key_id == key_id
    assert record.user_id == user_id
    assert record.method == "POST"
    assert record.path == "/api/v1/gateway/echo"
    assert record.status_code == 200
    assert record.latency_ms == 1.85
    assert record.client_ip == "10.0.0.1"
    assert record.timestamp == now
    assert record.__tablename__ == "usage_records"


def test_hourly_usage_rollup_model_attributes() -> None:
    """Verify HourlyUsageRollup aggregates and unique constraints."""
    key_id = uuid.uuid4()
    bucket_hour = datetime(2026, 10, 19, 2, 0, tzinfo=UTC)

    rollup = HourlyUsageRollup(
        key_id=key_id,
        bucket_hour=bucket_hour,
        total_requests=1000,
        success_requests=950,
        client_error_requests=30,
        rate_limited_requests=15,
        server_error_requests=5,
        avg_latency_ms=2.45,
        p95_latency_ms=8.10,
        p99_latency_ms=14.50,
    )

    assert rollup.key_id == key_id
    assert rollup.bucket_hour == bucket_hour
    assert rollup.total_requests == 1000
    assert rollup.success_requests == 950
    assert rollup.client_error_requests == 30
    assert rollup.rate_limited_requests == 15
    assert rollup.server_error_requests == 5
    assert rollup.avg_latency_ms == 2.45
    assert rollup.p95_latency_ms == 8.10
    assert rollup.p99_latency_ms == 14.50
    assert rollup.__tablename__ == "hourly_usage_rollups"
