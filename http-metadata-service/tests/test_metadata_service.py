"""
Tests for the metadata service (business logic layer).

Validates the orchestration between the HTTP client and repository,
including URL normalization, collect-and-store workflow, and
background collection error handling.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.services.metadata_service import (
    _normalize_url,
    collect_and_store_metadata,
    get_metadata,
    collect_metadata_background,
)
from app.services.http_client import URLUnreachableError, RequestTimeoutError


class TestNormalizeUrl:
    """Tests for URL normalization."""

    def test_strip_trailing_slash(self) -> None:
        """Remove trailing slash from URL."""
        assert _normalize_url("https://example.com/") == "https://example.com"

    def test_no_trailing_slash(self) -> None:
        """Keep URL unchanged if no trailing slash."""
        assert _normalize_url("https://example.com") == "https://example.com"

    def test_multiple_trailing_slashes(self) -> None:
        """Remove multiple trailing slashes."""
        assert _normalize_url("https://example.com///") == "https://example.com"

    def test_url_with_path(self) -> None:
        """Preserve path component while stripping trailing slash."""
        result = _normalize_url("https://example.com/page/")
        assert result == "https://example.com/page"


class TestCollectAndStoreMetadata:
    """Tests for the synchronous collect-and-store workflow."""

    @pytest.mark.asyncio
    @patch("app.services.metadata_service.insert_metadata", new_callable=AsyncMock)
    @patch("app.services.metadata_service.fetch_url_metadata", new_callable=AsyncMock)
    async def test_successful_collection(
        self,
        mock_fetch: AsyncMock,
        mock_insert: AsyncMock,
        sample_fetched_data: dict,
    ) -> None:
        """Successfully collect and store metadata."""
        mock_fetch.return_value = sample_fetched_data
        mock_insert.return_value = "https://example.com"

        result = await collect_and_store_metadata("https://example.com")

        assert result["url"] == "https://example.com"
        assert result["status_code"] == 200
        assert result["status"] == "completed"
        assert "created_at" in result
        assert "updated_at" in result

        mock_fetch.assert_called_once_with("https://example.com")
        mock_insert.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.metadata_service.fetch_url_metadata", new_callable=AsyncMock)
    async def test_fetch_failure_propagates(
        self,
        mock_fetch: AsyncMock,
    ) -> None:
        """Propagate HTTP client errors to the caller."""
        mock_fetch.side_effect = URLUnreachableError(
            url="https://example.com",
            reason="Connection refused",
        )

        with pytest.raises(URLUnreachableError):
            await collect_and_store_metadata("https://example.com")


class TestGetMetadata:
    """Tests for metadata retrieval."""

    @pytest.mark.asyncio
    @patch("app.services.metadata_service.find_metadata_by_url", new_callable=AsyncMock)
    async def test_cache_hit(
        self,
        mock_find: AsyncMock,
        sample_metadata_record: dict,
    ) -> None:
        """Return metadata record on cache hit."""
        mock_find.return_value = sample_metadata_record

        result = await get_metadata("https://example.com")

        assert result is not None
        assert result["url"] == "https://example.com"
        mock_find.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    @patch("app.services.metadata_service.find_metadata_by_url", new_callable=AsyncMock)
    async def test_cache_miss(self, mock_find: AsyncMock) -> None:
        """Return None on cache miss."""
        mock_find.return_value = None

        result = await get_metadata("https://example.com")

        assert result is None


class TestCollectMetadataBackground:
    """Tests for the background collection function."""

    @pytest.mark.asyncio
    @patch("app.services.metadata_service.collect_and_store_metadata", new_callable=AsyncMock)
    async def test_successful_background_collection(
        self,
        mock_collect: AsyncMock,
        sample_metadata_record: dict,
    ) -> None:
        """Successfully complete background collection."""
        mock_collect.return_value = sample_metadata_record

        # Should not raise — errors are caught internally
        await collect_metadata_background("https://example.com")

        mock_collect.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.metadata_service._store_failed_record", new_callable=AsyncMock)
    @patch("app.services.metadata_service.collect_and_store_metadata", new_callable=AsyncMock)
    async def test_background_collection_http_error(
        self,
        mock_collect: AsyncMock,
        mock_store_failed: AsyncMock,
    ) -> None:
        """Store a failed record when HTTP error occurs in background."""
        mock_collect.side_effect = URLUnreachableError(
            url="https://example.com",
            reason="Connection refused",
        )

        # Should not raise
        await collect_metadata_background("https://example.com")

        mock_store_failed.assert_called_once()
        call_args = mock_store_failed.call_args
        assert "https://example.com" in call_args[0][0]

    @pytest.mark.asyncio
    @patch("app.services.metadata_service._store_failed_record", new_callable=AsyncMock)
    @patch("app.services.metadata_service.collect_and_store_metadata", new_callable=AsyncMock)
    async def test_background_collection_unexpected_error(
        self,
        mock_collect: AsyncMock,
        mock_store_failed: AsyncMock,
    ) -> None:
        """Handle unexpected errors gracefully in background."""
        mock_collect.side_effect = RuntimeError("Unexpected failure")

        # Should not raise
        await collect_metadata_background("https://example.com")

        mock_store_failed.assert_called_once()


# ---------------------------------------------------------------------------
# Fixtures for this module (avoids conftest circular dependency)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_fetched_data() -> dict:
    """Sample data as returned by fetch_url_metadata."""
    return {
        "status_code": 200,
        "headers": {"content-type": "text/html"},
        "cookies": [],
        "page_source": "<html></html>",
        "content_length": 13,
    }


@pytest.fixture
def sample_metadata_record() -> dict:
    """Sample complete metadata record."""
    now = datetime.now(timezone.utc).isoformat()
    return {
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