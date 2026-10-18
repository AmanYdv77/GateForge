from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.api.dependencies.ratelimit import enforce_rate_limit
from gateforge.schemas.gateway import (
    GatewayEchoRequest,
    GatewayEchoResponse,
    GatewayVerifyResponse,
)
from gateforge.schemas.ratelimit import RateLimitDecision

router = APIRouter(prefix="/gateway", tags=["Gateway Edge Proxy"])


@router.get(
    "/verify",
    response_model=GatewayVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify API Key and Deduct Edge Quota",
    description="Sub-millisecond edge validation endpoint verifying incoming X-API-Key and quota diagnostics.",
)
async def verify_gateway_key(
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    rate_limit: RateLimitDecision = Depends(enforce_rate_limit),
) -> GatewayVerifyResponse:
    """Validate bearer key against distributed cache and enforce sliding-window quota."""
    return GatewayVerifyResponse(
        authenticated=True,
        key_id=auth_key.key_id,
        user_id=auth_key.user_id,
        scopes=auth_key.scopes,
        rate_limit_rpm=auth_key.rate_limit_rpm,
        cache_hit=auth_key.cache_hit,
        timestamp=datetime.now(UTC),
    )


@router.post(
    "/echo",
    response_model=GatewayEchoResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticated Echo Endpoint",
    description="Secure gateway endpoint that echoes client payload with authenticated identity and quota metrics.",
)
async def gateway_echo(
    request_data: GatewayEchoRequest,
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    rate_limit: RateLimitDecision = Depends(enforce_rate_limit),
) -> GatewayEchoResponse:
    """Echo incoming payload while verifying cryptographic identity and sliding-window limits."""
    return GatewayEchoResponse(
        status="ok",
        key_id=auth_key.key_id,
        user_id=auth_key.user_id,
        echo_payload=request_data.payload,
        remaining_quota=rate_limit.remaining,
        reset_seconds=rate_limit.reset_seconds,
        timestamp=datetime.now(UTC),
    )
