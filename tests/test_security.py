from gateforge.core.security import (
    generate_api_key,
    hash_api_key,
    mask_key_preview,
    verify_api_key,
)


def test_generate_api_key_format() -> None:
    """Validate that generated API keys conform to standard prefix and length."""
    full_key, key_hash, prefix, suffix = generate_api_key("gfg_live_")

    assert full_key.startswith("gfg_live_")
    assert len(full_key) >= 48
    assert len(key_hash) == 64  # SHA-256 hex string is 64 characters
    assert prefix == full_key[:12]
    assert suffix == full_key[-4:]


def test_hash_api_key_deterministic() -> None:
    """Validate that hashing the same key yields identical deterministic digests."""
    raw_key = "gfg_live_sample_token_for_testing_123456789"
    h1 = hash_api_key(raw_key)
    h2 = hash_api_key(raw_key)

    assert h1 == h2
    assert len(h1) == 64


def test_verify_api_key() -> None:
    """Verify constant-time validation accurately identifies matching and forged keys."""
    raw_key = "gfg_live_authenticated_token_value_secure"
    expected_hash = hash_api_key(raw_key)

    assert verify_api_key(raw_key, expected_hash) is True
    assert verify_api_key(raw_key + "_tampered", expected_hash) is False
    assert verify_api_key("gfg_live_completely_different", expected_hash) is False


def test_mask_key_preview() -> None:
    """Verify that masking produces clean masked string with only prefix and suffix visible."""
    prefix = "gfg_live_7a9f"
    suffix = "8f0a"
    masked = mask_key_preview(prefix, suffix)

    assert masked == "gfg_live_7a9f••••••••••••8f0a"
    assert prefix in masked
    assert suffix in masked
