from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.schemas.gateway import GatewayVerifyResponse

router = APIRouter(prefix="/gateway", tags=["Gateway Edge Proxy"])


@router.get(
    "/verify",
    response_model=GatewayVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify API Key and Retrieve Edge Quota",
    description="Sub-millisecond edge validation endpoint verifying incoming X-API-Key and quota diagnostics.",
)
async def verify_gateway_key(
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
) -> GatewayVerifyResponse:
    """Validate bearer key against distributed cache and return caller quota and scopes."""
    return GatewayVerifyResponse(
        authenticated=True,
        key_id=auth_key.key_id,
        user_id=auth_key.user_id,
        scopes=auth_key.scopes,
        rate_limit_rpm=auth_key.rate_limit_rpm,
        cache_hit=auth_key.cache_hit,
        timestamp=datetime.now(UTC),
    )
