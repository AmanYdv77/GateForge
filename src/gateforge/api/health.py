from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from gateforge.core.database import get_db_session

router = APIRouter(prefix="/health", tags=["Health & Observability"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, str]:
    """Liveness probe verifying application process is responsive."""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_probe(
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """Readiness probe performing live dependency checks against database."""
    checks: dict[str, str] = {}
    is_ready = True

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "reachable"
    except Exception as exc:
        is_ready = False
        checks["database"] = f"unreachable: {exc}"

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    overall_status = "ready" if is_ready else "not_ready"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "checks": checks,
        },
    )
