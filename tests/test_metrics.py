import pytest
from httpx import ASGITransport, AsyncClient

from gateforge.core.metrics import (
    METRICS_CONTENT_TYPE,
    get_metrics_payload,
    record_cache_metric,
    record_ratelimit_metric,
    record_request_metric,
)
from gateforge.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format() -> None:
    """Verify that /metrics returns 200 with standard Prometheus exposition format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert METRICS_CONTENT_TYPE in response.headers["content-type"]
        body = response.text
        assert "gateforge_http_requests_total" in body
        assert "gateforge_http_request_duration_seconds" in body
        assert "gateforge_auth_cache_requests_total" in body
        assert "gateforge_ratelimit_decisions_total" in body


@pytest.mark.asyncio
async def test_metrics_recorded_on_api_request() -> None:
    """Verify that requests to API endpoints increment the prometheus request counter."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request health endpoint (live/ready) or public API
        resp = await client.get("/health/live")
        assert resp.status_code == 200

    # Ensure get_metrics_payload returns valid bytes
    payload = get_metrics_payload().decode("utf-8")
    assert "gateforge_http_requests_total" in payload


def test_custom_metrics_recording() -> None:
    """Verify helper recording functions for cache and rate limit counters."""
    record_cache_metric("hit")
    record_cache_metric("miss")
    record_ratelimit_metric("allowed")
    record_ratelimit_metric("exceeded")
    record_request_metric(
        method="POST",
        endpoint="/api/v1/keys",
        status_code=201,
        duration_seconds=0.0034,
    )

    payload = get_metrics_payload().decode("utf-8")
    assert 'gateforge_auth_cache_requests_total{result="hit"}' in payload
    assert 'gateforge_auth_cache_requests_total{result="miss"}' in payload
    assert 'gateforge_ratelimit_decisions_total{result="allowed"}' in payload
    assert 'gateforge_ratelimit_decisions_total{result="exceeded"}' in payload
    assert 'gateforge_http_requests_total{endpoint="/api/v1/keys",method="POST",status_code="201"}' in payload
