from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class GatewayVerifyResponse(BaseModel):
    """Diagnostic response for edge authentication verification."""

    authenticated: bool = Field(default=True, description="Authentication success flag")
    key_id: UUID = Field(description="Unique API key UUID")
    user_id: UUID = Field(description="Owning user account UUID")
    scopes: list[str] = Field(description="Granted permission scopes")
    rate_limit_rpm: int = Field(description="Assigned rate limit RPM quota")
    cache_hit: bool = Field(
        description="True if identity was verified in sub-millisecond RAM, False if DB read-through occurred"
    )
    timestamp: datetime = Field(description="Verification timestamp in UTC")


class GatewayEchoRequest(BaseModel):
    """Optional arbitrary JSON payload for gateway echo route."""

    payload: dict[str, Any] = Field(default_factory=dict, description="Arbitrary client payload")


class GatewayEchoResponse(BaseModel):
    """Echo response demonstrating edge authentication and quota deduction."""

    status: str = Field(default="ok", description="Status confirmation")
    key_id: UUID = Field(description="Authenticated API key UUID")
    user_id: UUID = Field(description="Authenticated User UUID")
    echo_payload: dict[str, Any] = Field(description="Echoed client payload")
    remaining_quota: int = Field(description="Remaining quota in active sliding window")
    reset_seconds: int = Field(description="Seconds until sliding window quota resets")
    timestamp: datetime = Field(description="Execution timestamp in UTC")
