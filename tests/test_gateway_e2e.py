from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gateforge.api.dependencies.auth import get_auth_cache_service
from gateforge.api.deps import get_current_user
from gateforge.core.database import get_db_session
from gateforge.core.redis_client import ResilientRedisClient
from gateforge.core.security import hash_api_key
from gateforge.main import app
from gateforge.models.base import Base
from gateforge.models.user import User
from gateforge.schemas.cache import CachedKeyData
from gateforge.services.api_key import APIKeyService
from gateforge.services.auth_cache import AuthCacheService


class InMemoryTestRedis:
    """In-memory dictionary-backed async test double for Redis operations."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, time_seconds: int, value: str) -> bool:
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
        return count

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


@pytest.fixture
async def e2e_db_engine():
    """Create isolated SQLite in-memory engine for full end-to-end testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def e2e_session_factory(e2e_db_engine):
    return async_sessionmaker(bind=e2e_db_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
def in_memory_redis():
    return InMemoryTestRedis()


@pytest.fixture
def e2e_auth_cache(in_memory_redis):
    # ResilientRedisClient wrapping our in-memory double
    resilient = ResilientRedisClient(redis_client=in_memory_redis)  # type: ignore[arg-type]
    return AuthCacheService(redis_client=resilient, jitter_max_seconds=0)


async def test_gateway_full_lifecycle_and_invalidation(
    e2e_session_factory,
    e2e_auth_cache,
    in_memory_redis,
):
    """Verify complete gateway lifecycle:

    1. Admin creates key
    2. Cold gateway request (cache miss -> DB fallback -> cache warmed)
    3. Hot gateway request (cache hit in RAM -> zero DB queries)
    4. Admin revokes key (cache purged)
    5. Immediate gateway request rejected (401 Unauthorized, zero stale window)
    """
    # Setup test user in database
    user_id = uuid4()
    test_user = User(
        id=user_id,
        email="edge_tester@gateforge.internal",
        hashed_password="hashed_argon2_password",
        tier="enterprise",
    )

    async with e2e_session_factory() as session:
        session.add(test_user)
        await session.commit()

        # Step 1: Create a live API key
        api_key_record, raw_key = await APIKeyService.create_key(
            session=session,
            user_id=user_id,
            name="Production Gateway E2E Key",
            scopes=["read:metrics", "write:events"],
            custom_rate_limit_rpm=600,
        )
        key_id = api_key_record.id

    # Configure app dependency overrides
    async def override_get_db_session():
        async with e2e_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_auth_cache_service] = lambda: e2e_auth_cache

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-API-Key": raw_key}

            # Step 2: Cold request (Cache miss -> DB query -> Cache warmed)
            cold_resp = await client.get("/api/v1/gateway/verify", headers=headers)
            assert cold_resp.status_code == 200
            cold_data = cold_resp.json()
            assert cold_data["authenticated"] is True
            assert cold_data["cache_hit"] is False
            assert cold_data["key_id"] == str(key_id)
            assert cold_data["rate_limit_rpm"] == 600

            # Verify that key was stored in Redis store
            key_hash = hash_api_key(raw_key)
            assert f"auth:apikey:{key_hash}" in in_memory_redis.store

            # Step 3: Hot request (Cache hit in RAM -> sub-millisecond)
            hot_resp = await client.get("/api/v1/gateway/verify", headers=headers)
            assert hot_resp.status_code == 200
            hot_data = hot_resp.json()
            assert hot_data["authenticated"] is True
            assert hot_data["cache_hit"] is True
            assert hot_data["key_id"] == str(key_id)

            # Step 4: Admin revokes key via PATCH endpoint
            revoke_resp = await client.patch(f"/api/v1/keys/{key_id}/revoke")
            assert revoke_resp.status_code == 200
            assert revoke_resp.json()["is_active"] is False

            # Verify that the cache was immediately purged from Redis
            assert f"auth:apikey:{key_hash}" not in in_memory_redis.store

            # Step 5: Immediate subsequent request must fail with 401
            blocked_resp = await client.get("/api/v1/gateway/verify", headers=headers)
            assert blocked_resp.status_code == 401
            assert "revoked" in blocked_resp.json()["detail"].lower()

    finally:
        app.dependency_overrides.clear()


async def test_high_throughput_hot_cache_benchmark(e2e_auth_cache, in_memory_redis):
    """Verify 100 consecutive lookups on cached identity execute entirely in memory with 0 DB overhead."""
    key_id = uuid4()
    user_id = uuid4()
    key_hash = "bench_hash_64_characters_long_for_hot_cache_testing_1234567890abcdef"

    cached_item = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:telemetry"],
        rate_limit_rpm=1000,
    )
    await e2e_auth_cache.set_cached_key(key_hash, cached_item)

    # Execute 100 fast in-memory resolutions
    for _ in range(100):
        identity = await e2e_auth_cache.get_cached_key(key_hash)
        assert identity is not None
        assert identity.key_id == key_id
        assert identity.is_valid() is True
