"""
Tests for health check and root endpoints.

Validates service status reporting and documentation link availability.
"""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    @patch(
        "app.main.get_active_task_count",
        new_callable=AsyncMock,
        return_value=0,
    )
    async def test_health_check_healthy(
        self,
        mock_count: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return healthy status with zero active tasks."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["active_background_tasks"] == 0
        assert "service" in data
        assert "version" in data

    @pytest.mark.asyncio
    @patch(
        "app.main.get_active_task_count",
        new_callable=AsyncMock,
        return_value=3,
    )
    async def test_health_check_with_active_tasks(
        self,
        mock_count: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Report active background task count."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        assert response.json()["active_background_tasks"] == 3


class TestRootEndpoint:
    """Tests for the / root endpoint."""

    @pytest.mark.asyncio
    async def test_root_returns_service_info(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Return service information and documentation links."""
        response = await async_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "documentation" in data
        assert "endpoints" in data

    @pytest.mark.asyncio
    async def test_root_contains_doc_links(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Verify documentation links are present."""
        response = await async_client.get("/")

        docs = response.json()["documentation"]
        assert "swagger_ui" in docs
        assert "redoc" in docs
        assert "openapi_spec" in docs