from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from gateforge.core.config import Settings, get_settings

api_key_header_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Live API key with 'gfg_live_' prefix for authenticated edge requests",
)


async def extract_raw_api_key(
    raw_key: str | None = Security(api_key_header_scheme),
    settings: Settings = Depends(get_settings),
) -> str:
    """Extract and perform fast syntactic format validation on the incoming X-API-Key header."""
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key header 'X-API-Key' is missing",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    clean_key = raw_key.strip()
    prefix = settings.API_KEY_PREFIX

    if not clean_key.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid API key prefix; expected '{prefix}'",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate minimum required length (prefix + 32 base62 characters)
    if len(clean_key) < len(prefix) + 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed API key length",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return clean_key
