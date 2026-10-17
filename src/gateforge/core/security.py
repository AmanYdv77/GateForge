import hashlib
import secrets


def generate_api_key(prefix: str = "gfg_live_") -> tuple[str, str, str, str]:
    """Generate a high-entropy cryptographically secure API key.

    Returns:
        tuple containing:
            - full_key (str): The raw plaintext secret (shown once, never stored)
            - key_hash (str): Deterministic SHA-256 hash stored in database for O(1) lookup
            - key_prefix (str): First 12 characters for customer identification
            - key_suffix (str): Last 4 characters for customer identification
    """
    # 32 bytes of random entropy yields ~43 characters URL-safe base64 string
    entropy = secrets.token_urlsafe(32)
    full_key = f"{prefix}{entropy}"

    key_hash = hash_api_key(full_key)
    key_prefix = full_key[:12]
    key_suffix = full_key[-4:]

    return full_key, key_hash, key_prefix, key_suffix


def hash_api_key(raw_key: str) -> str:
    """Compute deterministic SHA-256 hex digest for lookup and comparison."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, expected_hash: str) -> bool:
    """Validate incoming API key against stored hash using constant-time comparison."""
    computed_hash = hash_api_key(raw_key)
    return secrets.compare_digest(computed_hash, expected_hash)


def mask_key_preview(key_prefix: str, key_suffix: str) -> str:
    """Format safe masked display preview for dashboard visualization."""
    return f"{key_prefix}••••••••••••{key_suffix}"
