from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from gateforge.models.api_key import APIKey
from gateforge.models.base import Base
from gateforge.models.user import User


@pytest.mark.asyncio
async def test_user_and_api_key_relationships() -> None:
    """Verify entity persistence, relationships, and cascading deletion."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        # Create user
        user = User(
            email="developer@example.com",
            hashed_password="secure_hashed_password_hash",
            tier="pro",
        )
        session.add(user)
        await session.commit()
        user_id = user.id

        # Create API Key for user
        api_key = APIKey(
            user_id=user_id,
            name="Primary Mobile Key",
            key_prefix="gfg_live_7a9f",
            key_suffix="8f0a",
            key_hash="a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
            scopes=["read:reports", "write:orders"],
            custom_rate_limit_rpm=1200,
            expires_at=datetime(2028, 1, 1, tzinfo=UTC),
        )
        session.add(api_key)
        await session.commit()
        api_key_id = api_key.id

        assert api_key.masked_display == "gfg_live_7a9f••••••••••••8f0a"
        assert api_key.scopes == ["read:reports", "write:orders"]
        assert api_key.custom_rate_limit_rpm == 1200

        # Query via separate query using selectinload
        result = await session.execute(
            select(User).options(selectinload(User.api_keys)).where(User.id == user_id)
        )
        loaded_user = result.scalar_one()
        assert len(loaded_user.api_keys) == 1
        assert loaded_user.api_keys[0].name == "Primary Mobile Key"

        # Cascade delete verification
        await session.delete(loaded_user)
        await session.commit()

        key_result = await session.execute(select(APIKey).where(APIKey.id == api_key_id))
        assert key_result.scalar_one_or_none() is None

    await test_engine.dispose()
