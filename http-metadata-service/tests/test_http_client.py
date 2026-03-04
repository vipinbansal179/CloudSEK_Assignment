"""
Tests for the HTTP client module.

Validates URL fetching, header/cookie extraction, and error handling
for various HTTP failure scenarios using mocked httpx responses.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.http_client import (
    fetch_url_metadata,
    _extract_headers,
    _extract_cookies,
    HTTPClientError,
    URLUnreachableError,
    RequestTimeoutError,
)


class TestExtractHeaders:
    """Tests for the header extraction helper."""

    def test_extract_simple_headers(self) -> None:
        """Extract headers from a mock response."""
        mock_response = MagicMock()
        mock_response.headers = httpx.Headers({
            "content-type": "text/html",
            "server": "nginx",
        })

        headers = _extract_headers(mock_response)

        assert headers["content-type"] == "text/html"
        assert headers["server"] == "nginx"

    def test_extract_empty_headers(self) -> None:
        """Handle a response with no headers."""
        mock_response = MagicMock()
        mock_response.headers = httpx.Headers({})

        headers = _extract_headers(mock_response)

        assert headers == {}


class TestExtractCookies:
    """Tests for the cookie extraction helper."""

    def test_extract_cookies_from_jar(self) -> None:
        """Extract cookies from a mock cookie jar."""
        mock_cookie = MagicMock()
        mock_cookie.name = "session_id"
        mock_cookie.value = "abc123"
        mock_cookie.domain = "example.com"
        mock_cookie.path = "/"

        mock_response = MagicMock()
        mock_response.cookies.jar = [mock_cookie]

        cookies = _extract_cookies(mock_response)

        assert len(cookies) == 1
        assert cookies[0]["name"] == "session_id"
        assert cookies[0]["value"] == "abc123"
        assert cookies[0]["domain"] == "example.com"

    def test_extract_empty_cookies(self) -> None:
        """Handle a response with no cookies."""
        mock_response = MagicMock()
        mock_response.cookies.jar = []

        cookies = _extract_cookies(mock_response)

        assert cookies == []

    def test_extract_cookie_with_missing_domain(self) -> None:
        """Handle cookies with None domain."""
        mock_cookie = MagicMock()
        mock_cookie.name = "test"
        mock_cookie.value = "val"
        mock_cookie.domain = None
        mock_cookie.path = None

        mock_response = MagicMock()
        mock_response.cookies.jar = [mock_cookie]

        cookies = _extract_cookies(mock_response)

        assert cookies[0]["domain"] == ""
        assert cookies[0]["path"] == "/"


class TestFetchUrlMetadata:
    """Tests for the main URL fetching function."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        """Successfully fetch metadata from a URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({
            "content-type": "text/html",
        })
        mock_response.cookies.jar = []
        mock_response.text = "<html><body>Hello</body></html>"

        with patch("app.services.http_client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            result = await fetch_url_metadata("https://example.com")

        assert result["status_code"] == 200
        assert result["headers"]["content-type"] == "text/html"
        assert result["cookies"] == []
        assert "Hello" in result["page_source"]
        assert result["content_length"] > 0

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        """Raise RequestTimeoutError on timeout."""
        with patch("app.services.http_client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.TimeoutException("Timed out")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            with pytest.raises(RequestTimeoutError):
                await fetch_url_metadata("https://slow-site.com")

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        """Raise URLUnreachableError on connection failure."""
        with patch("app.services.http_client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            with pytest.raises(URLUnreachableError):
                await fetch_url_metadata("https://unreachable.com")

    @pytest.mark.asyncio
    async def test_too_many_redirects(self) -> None:
        """Raise URLUnreachableError on excessive redirects."""
        with patch("app.services.http_client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.TooManyRedirects("Too many redirects")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            with pytest.raises(URLUnreachableError):
                await fetch_url_metadata("https://redirect-loop.com")

    @pytest.mark.asyncio
    async def test_invalid_url(self) -> None:
        """Raise HTTPClientError on invalid URL."""
        with patch("app.services.http_client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.side_effect = httpx.InvalidURL("Bad URL")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client_instance

            with pytest.raises(HTTPClientError) as exc_info:
                await fetch_url_metadata("not://valid")

            assert exc_info.value.error_code == "INVALID_URL"


class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_url_unreachable_error(self) -> None:
        """Verify URLUnreachableError attributes."""
        exc = URLUnreachableError(url="https://example.com", reason="Connection refused")
        assert "example.com" in exc.message
        assert "Connection refused" in exc.message
        assert exc.error_code == "URL_UNREACHABLE"

    def test_request_timeout_error(self) -> None:
        """Verify RequestTimeoutError attributes."""
        exc = RequestTimeoutError(url="https://example.com", timeout=30.0)
        assert "example.com" in exc.message
        assert "30.0" in exc.message
        assert exc.error_code == "REQUEST_TIMEOUT"

    def test_http_client_error_base(self) -> None:
        """Verify base HTTPClientError."""
        exc = HTTPClientError(message="Test error", error_code="TEST")
        assert exc.message == "Test error"
        assert exc.error_code == "TEST"
        assert str(exc) == "Test error"