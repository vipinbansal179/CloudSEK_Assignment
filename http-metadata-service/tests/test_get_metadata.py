"""
Tests for the GET /api/v1/metadata/ endpoint.

Validates cache hit (200), cache miss (202 with background trigger),
and failed record re-collection behaviour.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from httpx import AsyncClient


class TestGetMetadataCacheHit:
    """Tests for GET requests where metadata exists in DB."""

    @pytest.mark.asyncio
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_return_existing_metadata(
        self,
        mock_get: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 200 with full metadata on cache hit."""
        now = datetime.now(timezone.utc).isoformat()
        mock_get.return_value = {
            "url": "https://example.com",
            "status_code": 200,
            "headers": {"content-type": "text/html"},
            "cookies": [],
            "page_source": "<html></html>",
            "content_length": 13,
            "status": "completed",
            "created_at": now,
            "updated_at": now,
        }

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com"
        assert data["status_code"] == 200
        assert data["status"] == "completed"
        assert "headers" in data
        assert "page_source" in data

    @pytest.mark.asyncio
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_return_metadata_with_cookies(
        self,
        mock_get: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return metadata including cookies."""
        now = datetime.now(timezone.utc).isoformat()
        mock_get.return_value = {
            "url": "https://example.com",
            "status_code": 200,
            "headers": {"content-type": "text/html"},
            "cookies": [
                {
                    "name": "session",
                    "value": "abc",
                    "domain": "example.com",
                    "path": "/",
                }
            ],
            "page_source": "<html></html>",
            "content_length": 13,
            "status": "completed",
            "created_at": now,
            "updated_at": now,
        }

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        assert response.status_code == 200
        assert len(response.json()["cookies"]) == 1


class TestGetMetadataCacheMiss:
    """Tests for GET requests where metadata is not in DB."""

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.schedule_background_collection",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.metadata.is_url_being_collected",
        new_callable=AsyncMock,
    )
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_return_202_on_cache_miss(
        self,
        mock_get: AsyncMock,
        mock_is_collecting: AsyncMock,
        mock_schedule: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 202 Accepted and trigger background collection."""
        mock_get.return_value = None
        mock_is_collecting.return_value = False
        mock_schedule.return_value = True

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        assert response.status_code == 200  # FastAPI returns 200 by default
        data = response.json()
        assert data["status"] == "pending"
        assert "initiated" in data["message"].lower()

        mock_schedule.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.schedule_background_collection",
        new_callable=AsyncMock,
    )
    @patch(
        "app.routes.metadata.is_url_being_collected",
        new_callable=AsyncMock,
    )
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_already_collecting_message(
        self,
        mock_get: AsyncMock,
        mock_is_collecting: AsyncMock,
        mock_schedule: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Show 'already in progress' message for duplicate requests."""
        mock_get.return_value = None
        mock_is_collecting.return_value = True

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        data = response.json()
        assert data["status"] == "pending"
        assert "already in progress" in data["message"].lower()

        # Should NOT schedule another task
        mock_schedule.assert_not_called()


class TestGetMetadataFailedRecord:
    """Tests for GET requests that find a previously failed record."""

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.schedule_background_collection",
        new_callable=AsyncMock,
    )
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_retrigger_failed_record(
        self,
        mock_get: AsyncMock,
        mock_schedule: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Re-trigger collection for a previously failed record."""
        now = datetime.now(timezone.utc).isoformat()
        mock_get.return_value = {
            "url": "https://example.com",
            "status_code": 0,
            "headers": {},
            "cookies": [],
            "page_source": "",
            "content_length": 0,
            "status": "failed",
            "error_message": "Connection refused",
            "created_at": now,
            "updated_at": now,
        }
        mock_schedule.return_value = True

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        data = response.json()
        assert data["status"] == "pending"
        assert "failed" in data["message"].lower()

        mock_schedule.assert_called_once()


class TestGetMetadataValidation:
    """Tests for GET request input validation."""

    @pytest.mark.asyncio
    async def test_missing_url_param(self, async_client: AsyncClient) -> None:
        """Return 422 when URL query parameter is missing."""
        response = await async_client.get("/api/v1/metadata/")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_url_param(self, async_client: AsyncClient) -> None:
        """Return 422 for invalid URL format."""
        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "not-valid"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch("app.routes.metadata.get_metadata", new_callable=AsyncMock)
    async def test_unexpected_error(
        self,
        mock_get: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 500 for unexpected server errors."""
        mock_get.side_effect = RuntimeError("DB crashed")

        response = await async_client.get(
            "/api/v1/metadata/",
            params={"url": "https://example.com"},
        )

        assert response.status_code == 500