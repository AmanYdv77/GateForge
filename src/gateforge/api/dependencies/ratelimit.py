import structlog
from fastapi import Depends, HTTPException, Request, Response, status

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.core.ratelimit import SlidingWindowLimiter
from gateforge.core.redis import get_redis_client
from gateforge.schemas.ratelimit import RateLimitDecision

logger = structlog.get_logger(__name__)


def get_rate_limiter() -> SlidingWindowLimiter:
    """Dependency provider for SlidingWindowLimiter bound to shared Redis pool."""
    client = get_redis_client()
    return SlidingWindowLimiter(redis_client=client)


async def enforce_rate_limit(
    request: Request,
    response: Response,
    auth_key: AuthenticatedKey = Depends(get_current_api_key),
    limiter: SlidingWindowLimiter = Depends(get_rate_limiter),
) -> RateLimitDecision:
    """Evaluate sliding-window rate limit for caller and inject RFC 6585 compliance headers.

    Headers Injected:
        X-RateLimit-Limit: Total allowed requests per 60-second window.
        X-RateLimit-Remaining: Number of permitted requests left in current window.
        X-RateLimit-Reset: Seconds remaining until the sliding window quota fully replenishes.

    Raises:
        HTTPException (429): If caller quota is exhausted, with standard 'Retry-After' header.
    """
    decision = await limiter.check_rate_limit(
        identifier=str(auth_key.key_id),
        limit=auth_key.rate_limit_rpm,
        window_seconds=60,
    )

    # Standard RFC 6585 response headers
    rate_headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset_seconds),
    }

    # Inject headers into active response object
    for header_name, header_value in rate_headers.items():
        response.headers[header_name] = header_value

    if not decision.allowed:
        logger.warning(
            "rate_limit_exceeded_blocking_request",
            key_id=str(auth_key.key_id),
            limit=decision.limit,
            retry_after=decision.retry_after_seconds,
        )
        rate_headers["Retry-After"] = str(decision.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please throttle requests.",
            headers=rate_headers,
        )

    return decision
