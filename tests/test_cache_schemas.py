import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateforge.schemas.cache import CachedKeyData, build_auth_cache_key


def test_build_auth_cache_key():
    """Verify build_auth_cache_key constructs expected namespaced Redis key."""
    key_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    redis_key = build_auth_cache_key(key_hash)
    assert redis_key == f"auth:apikey:{key_hash}"


def test_cached_key_data_serialization_roundtrip():
    """Verify serialization to JSON and deserialization reconstructs identical model."""
    key_id = uuid4()
    user_id = uuid4()
    exp = datetime.now(UTC) + timedelta(hours=1)

    cached = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:reports", "write:webhooks"],
        rate_limit_rpm=120,
        expires_at=exp,
    )

    serialized = cached.to_json()
    assert isinstance(serialized, str)
    assert str(key_id) in serialized
    assert "read:reports" in serialized

    restored = CachedKeyData.from_json(serialized)
    assert restored.key_id == key_id
    assert restored.user_id == user_id
    assert restored.is_active is True
    assert restored.scopes == ["read:reports", "write:webhooks"]
    assert restored.rate_limit_rpm == 120
    assert restored.expires_at is not None


def test_cached_key_data_from_bytes():
    """Verify deserialization handles byte strings cleanly."""
    key_id = uuid4()
    user_id = uuid4()
    cached = CachedKeyData(key_id=key_id, user_id=user_id)
    raw_bytes = cached.to_json().encode("utf-8")

    restored = CachedKeyData.from_json(raw_bytes)
    assert restored.key_id == key_id


def test_cached_key_data_is_valid():
    """Verify is_valid logic for active/inactive and future/past expiration states."""
    key_id = uuid4()
    user_id = uuid4()
    now = datetime.now(UTC)

    # 1. Active with no expiration -> Valid
    active_no_exp = CachedKeyData(key_id=key_id, user_id=user_id, is_active=True)
    assert active_no_exp.is_valid(now) is True

    # 2. Inactive with no expiration -> Invalid
    inactive = CachedKeyData(key_id=key_id, user_id=user_id, is_active=False)
    assert inactive.is_valid(now) is False

    # 3. Active with future expiration -> Valid
    future_exp = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        expires_at=now + timedelta(minutes=10),
    )
    assert future_exp.is_valid(now) is True

    # 4. Active with past expiration -> Invalid
    past_exp = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        expires_at=now - timedelta(seconds=1),
    )
    assert past_exp.is_valid(now) is False


def test_cached_key_data_invalid_json():
    """Verify invalid JSON raises ValueError or ValidationError."""
    with pytest.raises((json.JSONDecodeError, ValidationError)):
        CachedKeyData.from_json("invalid-non-json-content")
