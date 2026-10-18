import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.api.dependencies.auth import get_auth_cache_service
from gateforge.api.deps import get_current_user
from gateforge.core.database import get_db_session
from gateforge.models.user import User
from gateforge.schemas.api_key import (
    APIKeyCreatedResponse,
    APIKeyCreateRequest,
    APIKeyResponse,
)
from gateforge.services.api_key import APIKeyService
from gateforge.services.auth_cache import AuthCacheService

router = APIRouter(prefix="/keys", tags=["API Keys Management"])


@router.post(
    "",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API Key",
    description="Generate a new cryptographic bearer key. The raw token is returned only once.",
)
async def create_api_key(
    request: APIKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> APIKeyCreatedResponse:
    """Generate and store a new API key record for the authenticated user."""
    api_key, raw_key = await APIKeyService.create_key(
        session=db,
        user_id=current_user.id,
        name=request.name,
        scopes=request.scopes,
        custom_rate_limit_rpm=request.custom_rate_limit_rpm,
        expires_at=request.expires_at,
    )

    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        raw_key=raw_key,
        masked_display=api_key.masked_display,
        scopes=api_key.scopes,
        custom_rate_limit_rpm=api_key.custom_rate_limit_rpm,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
    )


@router.get(
    "",
    response_model=list[APIKeyResponse],
    status_code=status.HTTP_200_OK,
    summary="List API Keys",
    description="List all active and revoked API keys belonging to the authenticated account.",
)
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[APIKeyResponse]:
    """Retrieve all API keys belonging to the active user."""
    keys = await APIKeyService.list_for_user(session=db, user_id=current_user.id)
    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            masked_display=key.masked_display,
            scopes=key.scopes,
            custom_rate_limit_rpm=key.custom_rate_limit_rpm,
            is_active=key.is_active,
            created_at=key.created_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
        )
        for key in keys
    ]


@router.get(
    "/{key_id}",
    response_model=APIKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get API Key Details",
    description="Retrieve details and status for a specific API key.",
)
async def get_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> APIKeyResponse:
    """Fetch details of an individual API key."""
    key = await APIKeyService.get_by_id(session=db, key_id=key_id)
    if key is None or key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found or access denied",
        )

    return APIKeyResponse(
        id=key.id,
        name=key.name,
        masked_display=key.masked_display,
        scopes=key.scopes,
        custom_rate_limit_rpm=key.custom_rate_limit_rpm,
        is_active=key.is_active,
        created_at=key.created_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
    )


@router.patch(
    "/{key_id}/revoke",
    response_model=APIKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke API Key",
    description="Immediately revoke an active API key, blocking all subsequent requests.",
)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    cache_service: AuthCacheService = Depends(get_auth_cache_service),
) -> APIKeyResponse:
    """Instantly revoke an API key and purge its cached entry."""
    key = await APIKeyService.get_by_id(session=db, key_id=key_id)
    if key is None or key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found or access denied",
        )

    revoked_key = await APIKeyService.revoke_key(
        session=db,
        key_id=key_id,
        cache_service=cache_service,
    )
    assert revoked_key is not None

    return APIKeyResponse(
        id=revoked_key.id,
        name=revoked_key.name,
        masked_display=revoked_key.masked_display,
        scopes=revoked_key.scopes,
        custom_rate_limit_rpm=revoked_key.custom_rate_limit_rpm,
        is_active=revoked_key.is_active,
        created_at=revoked_key.created_at,
        expires_at=revoked_key.expires_at,
        revoked_at=revoked_key.revoked_at,
    )
