import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.core.security import generate_api_key, hash_api_key
from gateforge.models.api_key import APIKey


class APIKeyService:
    """Service encapsulating API key cryptographic creation, storage, and lifecycle management."""

    @staticmethod
    async def create_key(
        session: AsyncSession,
        user_id: uuid.UUID,
        name: str,
        scopes: list[str] | None = None,
        custom_rate_limit_rpm: int | None = None,
        expires_at: datetime | None = None,
        prefix: str = "gfg_live_",
    ) -> tuple[APIKey, str]:
        """Generate a new cryptographic API key and store its deterministic hash.

        Returns:
            tuple[APIKey, str]: The persisted database record and the plaintext raw secret
            (shown only once upon creation).
        """
        raw_key, key_hash, prefix_part, suffix_part = generate_api_key(prefix=prefix)

        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_prefix=prefix_part,
            key_suffix=suffix_part,
            key_hash=key_hash,
            scopes=scopes or [],
            custom_rate_limit_rpm=custom_rate_limit_rpm,
            expires_at=expires_at,
            is_active=True,
        )

        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        return api_key, raw_key

    @staticmethod
    async def get_by_id(session: AsyncSession, key_id: uuid.UUID) -> APIKey | None:
        """Fetch an API key record by primary UUID key."""
        result = await session.execute(select(APIKey).where(APIKey.id == key_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_hash(session: AsyncSession, raw_or_hashed_key: str) -> APIKey | None:
        """Fetch an API key record by raw token or precomputed SHA-256 hash regardless of status."""
        key_hash = (
            raw_or_hashed_key
            if len(raw_or_hashed_key) == 64 and not raw_or_hashed_key.startswith("gfg_")
            else hash_api_key(raw_or_hashed_key)
        )
        query = select(APIKey).where(APIKey.key_hash == key_hash)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_hash(session: AsyncSession, raw_or_hashed_key: str) -> APIKey | None:
        """Look up an active, non-expired API key by raw token or precomputed SHA-256 hash."""
        # If input is raw token (longer than 64 hex characters or starts with prefix), hash it
        key_hash = (
            raw_or_hashed_key
            if len(raw_or_hashed_key) == 64 and not raw_or_hashed_key.startswith("gfg_")
            else hash_api_key(raw_or_hashed_key)
        )

        now = datetime.now(UTC)

        query = select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active.is_(True),
        )

        result = await session.execute(query)
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        # Check expiration with timezone normalization across PostgreSQL and SQLite
        if api_key.expires_at is not None:
            expires_at = (
                api_key.expires_at.replace(tzinfo=UTC)
                if api_key.expires_at.tzinfo is None
                else api_key.expires_at
            )
            if expires_at < now:
                return None

        return api_key

    @staticmethod
    async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[APIKey]:
        """List all API keys belonging to a specific user, ordered by creation date."""
        query = select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def revoke_key(session: AsyncSession, key_id: uuid.UUID) -> APIKey | None:
        """Revoke an active API key immediately and record revocation timestamp."""
        api_key = await APIKeyService.get_by_id(session, key_id)
        if api_key is None:
            return None

        api_key.is_active = False
        api_key.revoked_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(api_key)

        return api_key
