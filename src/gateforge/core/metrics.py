from typing import Final

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

METRICS_CONTENT_TYPE: Final[str] = CONTENT_TYPE_LATEST

# Dedicated registry to isolate application metrics
REGISTRY: Final[CollectorRegistry] = CollectorRegistry(auto_describe=True)

# Sub-millisecond to multi-second latency buckets
LATENCY_BUCKETS: Final[tuple[float, ...]] = (
    0.0005,
    0.001,
    0.002,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
)

REQUEST_COUNTER: Final[Counter] = Counter(
    "gateforge_http_requests_total",
    "Total HTTP requests processed by GateForge gateway",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

REQUEST_LATENCY: Final[Histogram] = Histogram(
    "gateforge_http_request_duration_seconds",
    "Request duration in seconds with sub-millisecond precision",
    ["method", "endpoint"],
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)

CACHE_COUNTER: Final[Counter] = Counter(
    "gateforge_auth_cache_requests_total",
    "Authentication cache lookup outcomes",
    ["result"],
    registry=REGISTRY,
)

RATELIMIT_COUNTER: Final[Counter] = Counter(
    "gateforge_ratelimit_decisions_total",
    "Sliding-window rate limiting quota evaluation outcomes",
    ["result"],
    registry=REGISTRY,
)


def record_request_metric(
    method: str,
    endpoint: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record request volume and duration into Prometheus collectors."""
    normalized_endpoint = endpoint if endpoint.startswith("/api/") else "other"
    REQUEST_COUNTER.labels(
        method=method.upper(),
        endpoint=normalized_endpoint,
        status_code=str(status_code),
    ).inc()
    REQUEST_LATENCY.labels(
        method=method.upper(),
        endpoint=normalized_endpoint,
    ).observe(duration_seconds)


def record_cache_metric(result: str) -> None:
    """Increment cache hit, miss, or invalid outcome counter."""
    CACHE_COUNTER.labels(result=result).inc()


def record_ratelimit_metric(result: str) -> None:
    """Increment rate limit evaluation outcome counter."""
    RATELIMIT_COUNTER.labels(result=result).inc()


def get_metrics_payload() -> bytes:
    """Generate Prometheus plaintext scrape payload."""
    return generate_latest(REGISTRY)
