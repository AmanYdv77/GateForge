import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from gateforge.api.dependencies.auth import AuthenticatedKey, get_current_api_key
from gateforge.core.ip_filter import (
    evaluate_ip_access,
    extract_client_ip,
    is_ip_allowed,
    parse_network,
)
from gateforge.schemas.api_key import APIKeyCreateRequest
from gateforge.schemas.cache import CachedKeyData
from gateforge.services.auth_cache import AuthCacheService


def test_parse_network_valid_and_invalid() -> None:
    """Verify robust parsing of single IPs, subnets, and malformed inputs."""
    net_v4 = parse_network("192.168.1.50")
    assert net_v4 is not None
    assert net_v4.prefixlen == 32

    net_cidr = parse_network("10.0.0.0/8")
    assert net_cidr is not None
    assert net_cidr.prefixlen == 8

    net_v6 = parse_network("2001:db8::1")
    assert net_v6 is not None
    assert net_v6.prefixlen == 128

    assert parse_network("") is None
    assert parse_network("invalid-ip-format") is None
    assert parse_network("999.999.999.999") is None


def test_is_ip_allowed_logic() -> None:
    """Verify IP matching across exact hosts, CIDR ranges, and empty allowlists."""
    # Empty list permits all traffic
    assert is_ip_allowed("192.168.1.1", []) is True

    # Matching single IP
    assert is_ip_allowed("192.168.1.100", ["192.168.1.100"]) is True
    assert is_ip_allowed("192.168.1.101", ["192.168.1.100"]) is False

    # Matching CIDR range
    assert is_ip_allowed("10.5.20.1", ["10.0.0.0/8"]) is True
    assert is_ip_allowed("172.16.0.1", ["10.0.0.0/8"]) is False

    # Multiple CIDRs
    allowlist = ["192.168.1.0/24", "10.0.0.0/8", "::1"]
    assert is_ip_allowed("192.168.1.55", allowlist) is True
    assert is_ip_allowed("10.254.1.1", allowlist) is True
    assert is_ip_allowed("::1", allowlist) is True
    assert is_ip_allowed("8.8.8.8", allowlist) is False

    # Invalid client IP
    assert is_ip_allowed("not-an-ip", ["10.0.0.0/8"]) is False
    assert is_ip_allowed(None, ["10.0.0.0/8"]) is False


def test_extract_client_ip_headers() -> None:
    """Verify client IP extraction priority: X-Forwarded-For > X-Real-IP > socket client."""
    # None request
    assert extract_client_ip(None) == "127.0.0.1"

    # X-Forwarded-For multi-hop proxy chain
    req_forwarded = MagicMock(spec=Request)
    req_forwarded.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
    assert extract_client_ip(req_forwarded) == "203.0.113.195"

    # X-Real-IP
    req_real = MagicMock(spec=Request)
    req_real.headers = {"x-real-ip": "198.51.100.4"}
    assert extract_client_ip(req_real) == "198.51.100.4"

    # Socket connection host fallback
    req_socket = MagicMock(spec=Request)
    req_socket.headers = {}
    client_mock = MagicMock()
    client_mock.host = "192.0.2.1"
    req_socket.client = client_mock
    assert extract_client_ip(req_socket) == "192.0.2.1"


def test_evaluate_ip_access_raises_forbidden() -> None:
    """Verify 403 Forbidden is raised when client IP is not in allowlist."""
    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "192.168.2.1"}

    # Permitted access does not raise
    evaluate_ip_access(req, ["192.168.2.0/24"])

    # Disallowed IP raises 403
    with pytest.raises(HTTPException) as exc_info:
        evaluate_ip_access(req, ["10.0.0.0/8"])
    assert exc_info.value.status_code == 403
    assert "not authorized for this API key" in exc_info.value.detail


def test_schema_ip_validation() -> None:
    """Verify Pydantic validation rejects malformed IP allowlist definitions."""
    # Valid allowlist
    valid_payload = APIKeyCreateRequest(
        name="Enterprise Key",
        allowed_ips=["192.168.1.0/24", "10.0.0.1", "2001:db8::/32"],
    )
    assert len(valid_payload.allowed_ips) == 3

    # Invalid entry
    with pytest.raises(ValueError, match="Invalid IP address or CIDR"):
        APIKeyCreateRequest(
            name="Bad Key",
            allowed_ips=["not_a_valid_ip"],
        )


def test_cached_key_data_serialization_with_allowed_ips() -> None:
    """Verify round-trip JSON serialization of CachedKeyData preserves allowed_ips."""
    key_id = uuid.uuid4()
    user_id = uuid.uuid4()
    data = CachedKeyData(
        key_id=key_id,
        user_id=user_id,
        is_active=True,
        scopes=["read:data"],
        allowed_ips=["192.168.1.0/24"],
        rate_limit_rpm=120,
    )
    json_str = data.to_json()
    assert "192.168.1.0/24" in json_str

    deserialized = CachedKeyData.from_json(json_str)
    assert deserialized.allowed_ips == ["192.168.1.0/24"]
    assert deserialized.rate_limit_rpm == 120


@pytest.mark.asyncio
async def test_auth_dependency_allows_valid_ip_cache_hit() -> None:
    """Verify get_current_api_key permits authorized client IP on cache hit."""
    raw_key = "gfg_live_allowedipcachehit1234567890123456"
    key_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_cache = MagicMock(spec=AuthCacheService)
    mock_cache.get_cached_key = AsyncMock(
        return_value=CachedKeyData(
            key_id=key_id,
            user_id=user_id,
            is_active=True,
            scopes=["read:orders"],
            allowed_ips=["192.168.1.0/24"],
            rate_limit_rpm=60,
        )
    )
    mock_db = AsyncMock()

    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "192.168.1.42"}
    req.state = MagicMock()

    auth_key = await get_current_api_key(
        request=req,
        raw_key=raw_key,
        db=mock_db,
        cache_service=mock_cache,
    )
    assert isinstance(auth_key, AuthenticatedKey)
    assert auth_key.key_id == key_id
    assert auth_key.allowed_ips == ["192.168.1.0/24"]


@pytest.mark.asyncio
async def test_auth_dependency_blocks_disallowed_ip_cache_hit() -> None:
    """Verify get_current_api_key raises 403 when client IP is disallowed on cache hit."""
    raw_key = "gfg_live_blockedipcachehit1234567890123456"
    mock_cache = MagicMock(spec=AuthCacheService)
    mock_cache.get_cached_key = AsyncMock(
        return_value=CachedKeyData(
            key_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            is_active=True,
            scopes=[],
            allowed_ips=["10.0.0.0/8"],
            rate_limit_rpm=60,
        )
    )
    mock_db = AsyncMock()

    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "192.168.1.1"}
    req.state = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await get_current_api_key(
            request=req,
            raw_key=raw_key,
            db=mock_db,
            cache_service=mock_cache,
        )
    assert exc.value.status_code == 403
    assert "Forbidden" in exc.value.detail
