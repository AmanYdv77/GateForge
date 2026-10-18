import secrets
from collections.abc import Awaitable, Callable

import structlog

from gateforge.core.config import Settings, get_settings
from gateforge.core.redis_client import ResilientRedisClient, get_resilient_redis
from gateforge.core.security import hash_api_key
from gateforge.schemas.cache import CachedKeyData, build_auth_cache_key

logger = structlog.get_logger(__name__)


class AuthCacheService:
    """High-performance Redis cache service for sub-millisecond edge API key authentication."""

    def __init__(
        self,
        redis_client: ResilientRedisClient | None = None,
        settings: Settings | None = None,
        jitter_max_seconds: int = 30,
    ) -> None:
        self._client: ResilientRedisClient = redis_client or get_resilient_redis()
        self._settings: Settings = settings or get_settings()
        self._jitter_max: int = jitter_max_seconds

    def calculate_ttl(self, base_ttl: int | None = None) -> int:
        """Calculate cache TTL with anti-stampede random jitter."""
        base = base_ttl or self._settings.AUTH_CACHE_TTL_SECONDS
        if self._jitter_max <= 0:
            return base
        jitter = secrets.randbelow(self._jitter_max + 1)
        return base + jitter

    async def get_cached_key(self, key_hash: str) -> CachedKeyData | None:
        """Retrieve and deserialize cached API key identity from Redis."""
        cache_key = build_auth_cache_key(key_hash)
        raw_val = await self._client.get(cache_key)
        if raw_val is None:
            return None

        try:
            return CachedKeyData.from_json(raw_val)
        except Exception as exc:
            logger.warning(
                "corrupt_auth_cache_payload",
                cache_key=cache_key,
                error=str(exc),
            )
            return None

    async def set_cached_key(
        self,
        key_hash: str,
        key_data: CachedKeyData,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Serialize and store API key identity in Redis with jittered expiration."""
        cache_key = build_auth_cache_key(key_hash)
        effective_ttl = self.calculate_ttl(ttl_seconds)
        serialized = key_data.to_json()

        success = await self._client.setex(cache_key, effective_ttl, serialized)
        if success:
            logger.debug(
                "auth_cache_key_stored",
                cache_key=cache_key,
                key_id=str(key_data.key_id),
                ttl=effective_ttl,
            )
        return success

    async def get_or_set_cached_key(
        self,
        key_hash: str,
        producer: Callable[[], Awaitable[CachedKeyData | None]],
        ttl_seconds: int | None = None,
    ) -> CachedKeyData | None:
        """Read-through cache pattern: check Redis first; on miss, invoke producer and warm cache."""
        cached = await self.get_cached_key(key_hash)
        if cached is not None:
            return cached

        data = await producer()
        if data is not None:
            await self.set_cached_key(key_hash, data, ttl_seconds)
        return data

    async def invalidate_key_by_hash(self, key_hash: str) -> bool:
        """Purge an API key immediately from the Redis authentication cache by hash."""
        cache_key = build_auth_cache_key(key_hash)
        deleted_count = await self._client.delete(cache_key)
        logger.info(
            "auth_cache_invalidated",
            cache_key=cache_key,
            deleted_count=deleted_count,
        )
        return deleted_count > 0

    async def invalidate_keys_by_hashes(self, key_hashes: list[str]) -> int:
        """Batch purge multiple API keys from Redis in a single atomic delete call."""
        if not key_hashes:
            return 0
        cache_keys = [build_auth_cache_key(kh) for kh in key_hashes]
        deleted_count = await self._client.delete(*cache_keys)
        logger.info(
            "auth_cache_batch_invalidated",
            keys_count=len(cache_keys),
            deleted_count=deleted_count,
        )
        return deleted_count

    async def invalidate_key(self, raw_or_hashed_key: str) -> bool:
        """Purge an API key from cache using raw key token or precomputed SHA-256 hash."""
        key_hash = (
            raw_or_hashed_key
            if len(raw_or_hashed_key) == 64 and not raw_or_hashed_key.startswith("gfg_")
            else hash_api_key(raw_or_hashed_key)
        )
        return await self.invalidate_key_by_hash(key_hash)
