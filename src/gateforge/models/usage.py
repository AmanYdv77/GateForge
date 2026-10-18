import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from gateforge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UsageRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Raw request telemetry log capturing gateway invocation metadata."""

    __tablename__ = "usage_records"

    request_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        doc="Correlation trace identifier from X-Request-ID header",
    )
    key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key pointing to APIKey entity if authenticated",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key pointing to User entity if authenticated",
    )
    method: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="HTTP method (e.g. GET, POST, DELETE)",
    )
    path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Requested gateway endpoint path",
    )
    status_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        doc="HTTP response status code (e.g. 200, 401, 429, 500)",
    )
    latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Total request round-trip latency measured in milliseconds",
    )
    client_ip: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Originating client IP address or proxy header",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
        doc="UTC timestamp when the request completed",
    )

    __table_args__ = (
        Index("ix_usage_records_key_timestamp", "key_id", "timestamp"),
        Index("ix_usage_records_user_timestamp", "user_id", "timestamp"),
        Index("ix_usage_records_status_timestamp", "status_code", "timestamp"),
    )


class HourlyUsageRollup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pre-aggregated hourly analytics rollup enabling sub-millisecond developer dashboard queries."""

    __tablename__ = "hourly_usage_rollups"

    key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key pointing to the target API key",
    )
    bucket_hour: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Start of the aggregated hour window in UTC",
    )
    total_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Total requests received within the hourly bucket",
    )
    success_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of 2xx success responses",
    )
    client_error_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of 4xx client errors (excluding 429)",
    )
    rate_limited_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of 429 Rate Limit Exceeded responses",
    )
    server_error_requests: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Count of 5xx internal server errors",
    )
    avg_latency_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="Arithmetic mean latency in milliseconds",
    )
    p95_latency_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="95th percentile latency in milliseconds",
    )
    p99_latency_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        doc="99th percentile latency in milliseconds",
    )

    __table_args__ = (
        UniqueConstraint("key_id", "bucket_hour", name="uq_hourly_rollup_key_hour"),
        Index("ix_hourly_rollup_key_hour", "key_id", "bucket_hour"),
    )
