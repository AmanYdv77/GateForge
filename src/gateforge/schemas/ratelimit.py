from pydantic import BaseModel, Field


class RateLimitDecision(BaseModel):
    """Evaluation result for an atomic sliding-window rate limit check."""

    allowed: bool = Field(description="True if request is within quota, False if rate limited")
    limit: int = Field(ge=1, description="Total permitted requests in the sliding window")
    remaining: int = Field(ge=0, description="Remaining requests allowed in current window")
    reset_seconds: int = Field(ge=0, description="Seconds until current window quota fully resets")
    retry_after_seconds: int = Field(
        default=0,
        ge=0,
        description="Seconds caller must wait before retrying (RFC 6585 Retry-After)",
    )
