from fastapi import APIRouter, Response, status

from gateforge.core.metrics import METRICS_CONTENT_TYPE, get_metrics_payload

router = APIRouter(tags=["Observability"])


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    summary="Prometheus Metrics Scrape Endpoint",
    description="Exposes live Prometheus application metrics, request throughput, latencies, and cache statistics.",
    include_in_schema=False,
)
def scrape_metrics() -> Response:
    """Return standard Prometheus formatted scrape exposition payload."""
    payload = get_metrics_payload()
    return Response(content=payload, media_type=METRICS_CONTENT_TYPE)
