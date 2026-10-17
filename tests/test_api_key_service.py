from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateforge.models.base import Base
from gateforge.models.user import User
from gateforge.services.api_key import APIKeyService


@pytest.fixture
async def session_factory():  # type: ignore[no-untyped-def]
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_create_and_lookup_key(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        user = User(email="service_test@example.com", hashed_password="pw", tier="pro")
        session.add(user)
        await session.commit()
        user_id = user.id

        # 1. Create Key
        api_key, raw_key = await APIKeyService.create_key(
            session=session,
            user_id=user_id,
            name="CI/CD Test Runner",
            scopes=["read:reports"],
            custom_rate_limit_rpm=300,
        )

        assert raw_key.startswith("gfg_live_")
        assert api_key.name == "CI/CD Test Runner"
        assert api_key.is_active is True
        assert api_key.key_prefix == raw_key[:12]
        assert api_key.key_suffix == raw_key[-4:]

        # 2. Lookup by Raw Secret
        found = await APIKeyService.get_active_by_hash(session, raw_key)
        assert found is not None
        assert found.id == api_key.id

        # 3. Lookup with non-existent token fails
        invalid = await APIKeyService.get_active_by_hash(session, "gfg_live_invalid_token")
        assert invalid is None


@pytest.mark.asyncio
async def test_key_revocation_lifecycle(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        user = User(email="revoke_test@example.com", hashed_password="pw")
        session.add(user)
        await session.commit()

        api_key, raw_key = await APIKeyService.create_key(
            session=session,
            user_id=user.id,
            name="Revocable Key",
        )

        # Confirm active
        active_key = await APIKeyService.get_active_by_hash(session, raw_key)
        assert active_key is not None

        # Revoke key
        revoked = await APIKeyService.revoke_key(session, api_key.id)
        assert revoked is not None
        assert revoked.is_active is False
        assert revoked.revoked_at is not None

        # Confirm lookup returns None for revoked key
        lookup_after_revoke = await APIKeyService.get_active_by_hash(session, raw_key)
        assert lookup_after_revoke is None


@pytest.mark.asyncio
async def test_expired_key_lookup(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        user = User(email="expired_test@example.com", hashed_password="pw")
        session.add(user)
        await session.commit()

        # Key expired 1 hour ago
        past_time = datetime.now(UTC) - timedelta(hours=1)
        api_key, raw_key = await APIKeyService.create_key(
            session=session,
            user_id=user.id,
            name="Expired Key",
            expires_at=past_time,
        )

        # Lookup must return None
        lookup = await APIKeyService.get_active_by_hash(session, raw_key)
        assert lookup is None
