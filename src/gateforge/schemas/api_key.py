import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIKeyCreateRequest(BaseModel):
    """Schema for requesting generation of a new cryptographic API key."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable label identifying this key",
        examples=["Mobile Production Client"],
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Granular permission strings attached to this key",
        examples=[["read:reports", "write:orders"]],
    )
    custom_rate_limit_rpm: int | None = Field(
        default=None,
        ge=1,
        le=100000,
        description="Optional custom request-per-minute quota override",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when this key expires",
    )


class APIKeyResponse(BaseModel):
    """Safe schema for presenting existing API keys without exposing secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    masked_display: str
    scopes: list[str]
    custom_rate_limit_rpm: int | None = None
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class APIKeyCreatedResponse(APIKeyResponse):
    """Schema returned strictly once upon key generation exposing raw secret."""

    raw_key: str = Field(
        ...,
        description="Plaintext bearer token. Shown only once and never stored in server memory.",
    )
