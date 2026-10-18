from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.api.dependencies.api_key_header import extract_raw_api_key
from gateforge.core.database import get_db_session
from gateforge.core.security import hash_api_key
from gateforge.schemas.cache import CachedKeyData
from gateforge.services.api_key import APIKeyService
from gateforge.services.auth_cache import AuthCacheService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedKey:
    """Authenticated caller identity and quota attributes yielded by edge authentication."""

    key_id: UUID
    user_id: UUID
    scopes: list[str]
    rate_limit_rpm: int
    cache_hit: bool


def get_auth_cache_service() -> AuthCacheService:
    """FastAPI dependency for obtaining an AuthCacheService instance."""
    return AuthCacheService()


async def get_current_api_key(
    raw_key: str = Depends(extract_raw_api_key),
    db: AsyncSession = Depends(get_db_session),
    cache_service: AuthCacheService = Depends(get_auth_cache_service),
) -> AuthenticatedKey:
    """Two-tier edge authentication: Redis RAM cache (<1ms) with PostgreSQL read-through fallback."""
    key_hash = hash_api_key(raw_key)

    # 1. Tier 1: Check ultra-fast distributed Redis cache
    cached = await cache_service.get_cached_key(key_hash)
    if cached is not None:
        if not cached.is_valid():
            logger.warning(
                "cached_api_key_invalid",
                key_id=str(cached.key_id),
                is_active=cached.is_active,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked or expired",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        logger.debug("auth_cache_hit", key_id=str(cached.key_id))
        return AuthenticatedKey(
            key_id=cached.key_id,
            user_id=cached.user_id,
            scopes=cached.scopes,
            rate_limit_rpm=cached.rate_limit_rpm,
            cache_hit=True,
        )

    # 2. Tier 2: Cache miss or Redis degraded -> Fallback to PostgreSQL
    logger.debug("auth_cache_miss_db_fallback", key_hash_prefix=key_hash[:8])
    api_key_entity = await APIKeyService.get_by_hash(db, key_hash)

    if api_key_entity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not api_key_entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has been revoked",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key_entity.expires_at is not None:
        now = datetime.now(UTC)
        exp = (
            api_key_entity.expires_at.replace(tzinfo=UTC)
            if api_key_entity.expires_at.tzinfo is None
            else api_key_entity.expires_at
        )
        if exp < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    rate_limit = api_key_entity.custom_rate_limit_rpm or 60

    # Warm Redis cache asynchronously for subsequent edge requests
    cache_payload = CachedKeyData(
        key_id=api_key_entity.id,
        user_id=api_key_entity.user_id,
        is_active=api_key_entity.is_active,
        scopes=list(api_key_entity.scopes),
        rate_limit_rpm=rate_limit,
        expires_at=api_key_entity.expires_at,
    )
    await cache_service.set_cached_key(key_hash, cache_payload)

    return AuthenticatedKey(
        key_id=api_key_entity.id,
        user_id=api_key_entity.user_id,
        scopes=list(api_key_entity.scopes),
        rate_limit_rpm=rate_limit,
        cache_hit=False,
    )
