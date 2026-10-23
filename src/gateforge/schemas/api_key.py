import ipaddress
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_ip_or_cidr(entry: str) -> None:
    cleaned = entry.strip()
    if not cleaned:
        raise ValueError("IP address or CIDR entry cannot be blank")
    try:
        if "/" in cleaned:
            ipaddress.ip_network(cleaned, strict=False)
        else:
            ipaddress.ip_address(cleaned)
    except ValueError as exc:
        raise ValueError(f"Invalid IP address or CIDR notation: '{cleaned}'") from exc


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
    allowed_ips: list[str] = Field(
        default_factory=list,
        description="Optional enterprise IP allowlist with CIDR blocks or single IPs (e.g. 192.168.1.0/24)",
        examples=[["192.168.1.0/24", "10.0.0.5"]],
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

    @field_validator("allowed_ips")
    @classmethod
    def validate_allowed_ips(cls, ips: list[str]) -> list[str]:
        """Ensure all provided IP allowlist entries are valid IPv4/IPv6 addresses or CIDRs."""
        for entry in ips:
            _validate_ip_or_cidr(entry)
        return [entry.strip() for entry in ips]


class APIKeyResponse(BaseModel):
    """Safe schema for presenting existing API keys without exposing secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    masked_display: str
    scopes: list[str]
    allowed_ips: list[str] = Field(default_factory=list)
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
