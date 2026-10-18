from uuid import UUID

from pydantic import BaseModel, Field


class QuotaUtilization(BaseModel):
    """Real-time quota utilization state and threshold alarm flags."""

    key_id: UUID = Field(description="Target API key unique identifier")
    tier: str = Field(description="Resolved tier (free, pro, enterprise)")
    rpm_limit: int = Field(description="Configured requests per minute capacity")
    current_usage: int = Field(description="Active requests logged in current sliding window")
    utilization_percent: float = Field(description="Calculated consumption percentage (0.0 to 100.0+)")
    warning_threshold: str | None = Field(
        default=None,
        description="Threshold status: None, WARNING_80, CRITICAL_95, or EXHAUSTED_100",
    )
    is_throttled: bool = Field(default=False, description="Whether key is currently rate-limited")
