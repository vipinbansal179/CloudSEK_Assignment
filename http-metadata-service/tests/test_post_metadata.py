"""
Tests for the POST /api/v1/metadata/ endpoint.

Validates successful metadata creation, error handling for
unreachable URLs, timeouts, and invalid input.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from httpx import AsyncClient


class TestPostMetadataSuccess:
    """Tests for successful POST requests."""

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.collect_and_store_metadata",
        new_callable=AsyncMock,
    )
    async def test_create_metadata_success(
        self,
        mock_collect: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Successfully create a metadata record."""
        now = datetime.now(timezone.utc).isoformat()
        mock_collect.return_value = {
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

        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "completed"
        assert data["url"] == "https://example.com"
        assert data["data"] is not None
        assert data["data"]["status_code"] == 200

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.collect_and_store_metadata",
        new_callable=AsyncMock,
    )
    async def test_create_metadata_with_cookies(
        self,
        mock_collect: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Create metadata record that includes cookies."""
        now = datetime.now(timezone.utc).isoformat()
        mock_collect.return_value = {
            "url": "https://example.com",
            "status_code": 200,
            "headers": {"content-type": "text/html"},
            "cookies": [
                {
                    "name": "session",
                    "value": "abc123",
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

        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 201
        cookies = response.json()["data"]["cookies"]
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"


class TestPostMetadataErrors:
    """Tests for POST request error handling."""

    @pytest.mark.asyncio
    async def test_invalid_url_format(self, async_client: AsyncClient) -> None:
        """Return 422 for malformed URL."""
        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "not-a-valid-url"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_url_field(self, async_client: AsyncClient) -> None:
        """Return 422 when URL field is missing."""
        response = await async_client.post(
            "/api/v1/metadata/",
            json={},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_body(self, async_client: AsyncClient) -> None:
        """Return 422 for empty request body."""
        response = await async_client.post(
            "/api/v1/metadata/",
            content="",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.collect_and_store_metadata",
        new_callable=AsyncMock,
    )
    async def test_url_unreachable(
        self,
        mock_collect: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 502 when target URL is unreachable."""
        from app.services.http_client import URLUnreachableError

        mock_collect.side_effect = URLUnreachableError(
            url="https://unreachable.com",
            reason="Connection refused",
        )

        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "https://unreachable.com"},
        )

        assert response.status_code == 502

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.collect_and_store_metadata",
        new_callable=AsyncMock,
    )
    async def test_request_timeout(
        self,
        mock_collect: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 504 when request to target URL times out."""
        from app.services.http_client import RequestTimeoutError

        mock_collect.side_effect = RequestTimeoutError(
            url="https://slow-site.com",
            timeout=30.0,
        )

        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "https://slow-site.com"},
        )

        assert response.status_code == 504

    @pytest.mark.asyncio
    @patch(
        "app.routes.metadata.collect_and_store_metadata",
        new_callable=AsyncMock,
    )
    async def test_unexpected_error(
        self,
        mock_collect: AsyncMock,
        async_client: AsyncClient,
    ) -> None:
        """Return 500 for unexpected server errors."""
        mock_collect.side_effect = RuntimeError("Unexpected failure")

        response = await async_client.post(
            "/api/v1/metadata/",
            json={"url": "https://example.com"},
        )

        assert response.status_code == 500