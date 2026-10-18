import structlog

from gateforge.core.config import Settings, get_settings
from gateforge.models.api_key import APIKey
from gateforge.models.user import User

logger = structlog.get_logger(__name__)


class QuotaResolver:
    """Hierarchical rate limit quota resolver for multi-tenant gateway callers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings or get_settings()

    def resolve_tier_quota(self, tier: str | None) -> int:
        """Resolve baseline rate limit RPM based on user account subscription tier."""
        normalized_tier = (tier or "free").strip().lower()

        if normalized_tier == "enterprise":
            return self._settings.RATE_LIMIT_ENTERPRISE_RPM
        elif normalized_tier == "pro":
            return self._settings.RATE_LIMIT_PRO_RPM
        elif normalized_tier == "free":
            return self._settings.RATE_LIMIT_FREE_RPM
        else:
            logger.warning(
                "unrecognized_account_tier_fallback_to_free",
                tier=tier,
                fallback_rpm=self._settings.RATE_LIMIT_FREE_RPM,
            )
            return self._settings.RATE_LIMIT_FREE_RPM

    def resolve_effective_quota(
        self,
        custom_rate_limit_rpm: int | None = None,
        user_tier: str | None = None,
    ) -> int:
        """Resolve effective quota: explicit key-level limit overrides account tier baseline."""
        if custom_rate_limit_rpm is not None and custom_rate_limit_rpm > 0:
            return custom_rate_limit_rpm
        return self.resolve_tier_quota(user_tier)

    def resolve_for_key_and_user(
        self,
        api_key: APIKey,
        user: User | None = None,
    ) -> int:
        """Convenience method resolving quota directly from SQLAlchemy entity models."""
        user_tier = user.tier if user else None
        return self.resolve_effective_quota(
            custom_rate_limit_rpm=api_key.custom_rate_limit_rpm,
            user_tier=user_tier,
        )
