from datetime import datetime
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
