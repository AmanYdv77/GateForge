import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from gateforge.core.metrics import record_request_metric
from gateforge.core.telemetry_queue import get_telemetry_queue
from gateforge.schemas.telemetry import RequestTelemetry

logger = structlog.get_logger(__name__)

EXCLUDED_PATHS: frozenset[str] = frozenset({
    "/health/live",
    "/health/ready",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
})


class TelemetryMiddleware(BaseHTTPMiddleware):
    """High-precision request timing, Prometheus metrics, and non-blocking telemetry ingestion middleware."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # 1. Propagate or assign unique correlation ID
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id

        # 2. Capture high-resolution monotonic start time
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self._record_telemetry(request, request_id, 500, latency_ms)
            record_request_metric(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
                duration_seconds=latency_ms / 1000.0,
            )
            raise

        # 3. Calculate latency in milliseconds
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 4. Inject standard diagnostic propagation headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{latency_ms:.2f}ms"

        # 5. Non-blocking telemetry buffering and Prometheus tracking
        self._record_telemetry(request, request_id, status_code, latency_ms)
        record_request_metric(
            method=request.method,
            endpoint=request.url.path,
            status_code=status_code,
            duration_seconds=latency_ms / 1000.0,
        )

        return response

    def _record_telemetry(
        self,
        request: Request,
        request_id: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        """Enqueue telemetry payload if route is not explicitly excluded."""
        if request.url.path in EXCLUDED_PATHS:
            return

        key_id = getattr(request.state, "api_key_id", None)
        user_id = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else None

        telemetry = RequestTelemetry(
            request_id=request_id,
            key_id=key_id,
            user_id=user_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            latency_ms=latency_ms,
            client_ip=client_ip,
        )
        get_telemetry_queue().enqueue_nowait(telemetry)
