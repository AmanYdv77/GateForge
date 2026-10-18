from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RequestTelemetry(BaseModel):
    """Raw telemetry metric captured for each gateway request."""

    request_id: str = Field(description="Unique correlation ID for tracing")
    key_id: UUID | None = Field(default=None, description="API key UUID if authenticated")
    user_id: UUID | None = Field(default=None, description="Owning user UUID if authenticated")
    method: str = Field(description="HTTP method (GET, POST, etc.)")
    path: str = Field(description="Request URL path")
    status_code: int = Field(description="HTTP response status code")
    latency_ms: float = Field(ge=0.0, description="Server request duration in milliseconds")
    client_ip: str | None = Field(default=None, description="Originating client IP address")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp in UTC",
    )
