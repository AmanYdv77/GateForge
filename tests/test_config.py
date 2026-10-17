from gateforge.core.config import Settings, get_settings


def test_default_settings() -> None:
    """Validate default configuration parameters and boundaries."""
    settings = Settings()

    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is False
    assert settings.API_KEY_PREFIX == "gfg_live_"
    assert settings.DB_POOL_SIZE == 20
    assert settings.REDIS_MAX_CONNECTIONS == 50
    assert settings.RATE_LIMIT_FREE_RPM == 60
    assert settings.RATE_LIMIT_PRO_RPM == 600
    assert settings.RATE_LIMIT_ENTERPRISE_RPM == 6000


def test_get_settings_singleton() -> None:
    """Validate that get_settings provides a cached singleton reference."""
    s1 = get_settings()
    s2 = get_settings()

    assert s1 is s2


def test_custom_settings_override() -> None:
    """Validate that custom parameters can be provided explicitly."""
    custom = Settings(
        ENVIRONMENT="staging",
        DEBUG=True,
        RATE_LIMIT_FREE_RPM=100,
    )

    assert custom.ENVIRONMENT == "staging"
    assert custom.DEBUG is True
    assert custom.RATE_LIMIT_FREE_RPM == 100
