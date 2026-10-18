from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsOverview(BaseModel):
    """Aggregated usage and performance metrics over a requested time window."""

    total_requests: int = Field(default=0, description="Total requests processed")
    successful_requests: int = Field(default=0, description="Total 2xx successful requests")
    client_error_requests: int = Field(default=0, description="Total 4xx client errors (excluding 429)")
    rate_limited_requests: int = Field(default=0, description="Total 429 Rate Limit Exceeded events")
    server_error_requests: int = Field(default=0, description="Total 5xx server errors")
    avg_latency_ms: float = Field(default=0.0, description="Arithmetic mean response latency")
    p95_latency_ms: float = Field(default=0.0, description="95th percentile response latency")
    p99_latency_ms: float = Field(default=0.0, description="99th percentile response latency")


class TimeSeriesPoint(BaseModel):
    """Single discrete time bucket data point for developer analytics charts."""

    bucket_timestamp: datetime = Field(description="Window start timestamp in UTC")
    total_requests: int = Field(default=0, description="Total requests within bucket")
    success_requests: int = Field(default=0, description="Successful requests within bucket")
    error_requests: int = Field(default=0, description="Error requests within bucket")
    rate_limited_requests: int = Field(default=0, description="429 rate-limited count")
    avg_latency_ms: float = Field(default=0.0, description="Mean latency in milliseconds")


class AnalyticsTimeSeriesResponse(BaseModel):
    """Complete time-series trend collection response."""

    points: list[TimeSeriesPoint] = Field(default_factory=list, description="Ordered time series intervals")
