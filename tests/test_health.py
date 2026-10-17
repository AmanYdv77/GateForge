from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateforge.core.database import get_db_session
from gateforge.main import create_app


@pytest.mark.asyncio
async def test_liveness_probe() -> None:
    """Verify that liveness probe returns HTTP 200 OK and alive status."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_probe_healthy() -> None:
    """Verify readiness probe returns 200 OK when database is reachable."""
    app = create_app()

    class MockHealthySession:
        async def execute(self, statement: Any) -> int:
            return 1

    async def mock_get_healthy_db() -> Any:
        yield MockHealthySession()

    app.dependency_overrides[get_db_session] = mock_get_healthy_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "reachable"


@pytest.mark.asyncio
async def test_readiness_probe_unhealthy() -> None:
    """Verify readiness probe returns 503 Service Unavailable when database fails."""
    app = create_app()

    class MockFailingSession:
        async def execute(self, statement: Any) -> int:
            raise ConnectionError("Database network timeout")

    async def mock_get_failing_db() -> Any:
        yield MockFailingSession()

    app.dependency_overrides[get_db_session] = mock_get_failing_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "unreachable" in data["checks"]["database"]
