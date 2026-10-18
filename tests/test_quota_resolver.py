from uuid import uuid4

from gateforge.core.config import Settings
from gateforge.models.api_key import APIKey
from gateforge.models.user import User
from gateforge.services.quota_resolver import QuotaResolver


def test_resolve_tier_quotas_standard():
    """Verify standard subscription tier rate limits are mapped properly."""
    settings = Settings(
        RATE_LIMIT_FREE_RPM=60,
        RATE_LIMIT_PRO_RPM=600,
        RATE_LIMIT_ENTERPRISE_RPM=6000,
    )
    resolver = QuotaResolver(settings)

    assert resolver.resolve_tier_quota("free") == 60
    assert resolver.resolve_tier_quota("pro") == 600
    assert resolver.resolve_tier_quota("enterprise") == 6000
    assert resolver.resolve_tier_quota("Enterprise") == 6000
    assert resolver.resolve_tier_quota("PRO") == 600


def test_resolve_tier_quota_unknown_fallback():
    """Verify unrecognized or None tier safely falls back to free tier limit."""
    settings = Settings(RATE_LIMIT_FREE_RPM=50)
    resolver = QuotaResolver(settings)

    assert resolver.resolve_tier_quota("unknown_tier_xyz") == 50
    assert resolver.resolve_tier_quota(None) == 50


def test_resolve_effective_quota_custom_override():
    """Verify custom key limit overrides user account tier default."""
    resolver = QuotaResolver()

    # Pro tier default is 600, but key has custom 1200 RPM
    effective = resolver.resolve_effective_quota(
        custom_rate_limit_rpm=1200,
        user_tier="pro",
    )
    assert effective == 1200


def test_resolve_effective_quota_fallback_to_tier():
    """Verify when custom limit is None or 0, account tier is used."""
    resolver = QuotaResolver()

    assert resolver.resolve_effective_quota(custom_rate_limit_rpm=None, user_tier="pro") == 600
    assert resolver.resolve_effective_quota(custom_rate_limit_rpm=0, user_tier="enterprise") == 6000


def test_resolve_for_key_and_user_entities():
    """Verify resolution directly from ORM entity models."""
    resolver = QuotaResolver()
    user = User(id=uuid4(), email="user@test.com", tier="pro")

    key_without_override = APIKey(
        id=uuid4(),
        user_id=user.id,
        name="Key 1",
        key_prefix="gfg_live_111",
        key_suffix="2222",
        key_hash="hash1",
        custom_rate_limit_rpm=None,
    )
    assert resolver.resolve_for_key_and_user(key_without_override, user) == 600

    key_with_override = APIKey(
        id=uuid4(),
        user_id=user.id,
        name="Key 2",
        key_prefix="gfg_live_333",
        key_suffix="4444",
        key_hash="hash2",
        custom_rate_limit_rpm=3000,
    )
    assert resolver.resolve_for_key_and_user(key_with_override, user) == 3000
