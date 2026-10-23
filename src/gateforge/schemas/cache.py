import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


def build_auth_cache_key(key_hash: str) -> str:
    """Generate standardized Redis cache namespace key for an API key hash."""
    return f"auth:apikey:{key_hash}"


class CachedKeyData(BaseModel):
    """Normalized payload representing an authenticated API key identity cached in Redis."""

    key_id: UUID = Field(description="Unique API key identifier")
    user_id: UUID = Field(description="Owner user identifier")
    is_active: bool = Field(default=True, description="Active status flag")
    scopes: list[str] = Field(default_factory=list, description="Authorized permission scopes")
    allowed_ips: list[str] = Field(
        default_factory=list,
        description="Enterprise IP allowlist containing CIDR blocks or single IPs",
    )
    rate_limit_rpm: int = Field(default=60, ge=1, description="Assigned rate limit in RPM")
    expires_at: datetime | None = Field(default=None, description="Optional UTC expiration timestamp")

    def is_valid(self, now: datetime | None = None) -> bool:
        """Verify whether the cached key is active and has not expired."""
        if not self.is_active:
            return False
        if self.expires_at is not None:
            current_time = now or datetime.now(UTC)
            # Ensure timezone awareness for comparison
            exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
            if current_time >= exp:
                return False
        return True

    def to_json(self) -> str:
        """Serialize cached key identity into a compact JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw_json: str | bytes) -> "CachedKeyData":
        """Deserialize raw JSON payload into a validated CachedKeyData model."""
        if isinstance(raw_json, bytes):
            raw_json = raw_json.decode("utf-8")
        parsed: dict[str, Any] = json.loads(raw_json)
        return cls.model_validate(parsed)
