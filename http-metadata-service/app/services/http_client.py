"""
Async HTTP client for fetching URL metadata.

Responsible for making outbound HTTP requests to target URLs
and extracting headers, cookies, and page source content.
This module handles all I/O-bound HTTP operations efficiently
using httpx's async client.
"""

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.metadata import CookieData

logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Base exception for HTTP client errors."""

    def __init__(self, message: str, error_code: str = "HTTP_CLIENT_ERROR") -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class URLUnreachableError(HTTPClientError):
    """Raised when the target URL cannot be reached."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            message=f"URL '{url}' is unreachable: {reason}",
            error_code="URL_UNREACHABLE",
        )


class RequestTimeoutError(HTTPClientError):
    """Raised when the HTTP request times out."""

    def __init__(self, url: str, timeout: float) -> None:
        super().__init__(
            message=f"Request to '{url}' timed out after {timeout} seconds.",
            error_code="REQUEST_TIMEOUT",
        )


class InvalidResponseError(HTTPClientError):
    """Raised when the server returns an unexpected response."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            message=f"Invalid response from '{url}': {reason}",
            error_code="INVALID_RESPONSE",
        )


def _extract_cookies(response: httpx.Response) -> list[dict[str, str]]:
    """
    Extract cookies from an httpx Response object.

    Iterates through the response cookie jar and converts each
    cookie into a structured dictionary.

    Args:
        response: The httpx response object.

    Returns:
        A list of cookie dictionaries.
    """
    cookies: list[dict[str, str]] = []

    for cookie in response.cookies.jar:
        cookies.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain or "",
                "path": cookie.path or "/",
            }
        )

    return cookies


def _extract_headers(response: httpx.Response) -> dict[str, str]:
    """
    Extract headers from an httpx Response object.

    Converts httpx Headers (which can have multiple values per key)
    into a simple string-to-string dictionary. For duplicate header
    names, the last value is kept.

    Args:
        response: The httpx response object.

    Returns:
        A dictionary of header name-value pairs.
    """
    return {key: value for key, value in response.headers.items()}


async def fetch_url_metadata(url: str) -> dict[str, Any]:
    """
    Fetch metadata (headers, cookies, page source) from a given URL.

    Performs an async HTTP GET request to the target URL and extracts
    all relevant metadata. Handles common failure scenarios including
    timeouts, connection errors, and invalid URLs.

    Args:
        url: The target URL to fetch metadata from.

    Returns:
        A dictionary containing:
            - status_code: HTTP status code
            - headers: Response headers
            - cookies: List of cookie dictionaries
            - page_source: Raw page content
            - content_length: Size of page source in bytes

    Raises:
        URLUnreachableError: If the URL cannot be reached.
        RequestTimeoutError: If the request exceeds the configured timeout.
        HTTPClientError: For other unexpected HTTP errors.
    """
    settings = get_settings()

    logger.info("Fetching metadata for URL: %s", url)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_request_timeout),
            follow_redirects=True,
            max_redirects=settings.http_max_redirects,
            headers={"User-Agent": settings.http_user_agent},
        ) as client:
            response = await client.get(url)

        # Extract all metadata components
        headers = _extract_headers(response)
        cookies = _extract_cookies(response)
        page_source = response.text

        metadata = {
            "status_code": response.status_code,
            "headers": headers,
            "cookies": cookies,
            "page_source": page_source,
            "content_length": len(page_source.encode("utf-8")),
        }

        logger.info(
            "Successfully fetched metadata for URL: %s (status: %d, size: %d bytes)",
            url,
            response.status_code,
            metadata["content_length"],
        )

        return metadata

    except httpx.TimeoutException as exc:
        logger.warning("Timeout while fetching URL '%s': %s", url, str(exc))
        raise RequestTimeoutError(url=url, timeout=settings.http_request_timeout)

    except httpx.ConnectError as exc:
        logger.warning("Connection error for URL '%s': %s", url, str(exc))
        raise URLUnreachableError(url=url, reason=str(exc))

    except httpx.TooManyRedirects as exc:
        logger.warning("Too many redirects for URL '%s': %s", url, str(exc))
        raise URLUnreachableError(
            url=url,
            reason=f"Exceeded maximum redirects ({settings.http_max_redirects})",
        )

    except httpx.InvalidURL as exc:
        logger.warning("Invalid URL '%s': %s", url, str(exc))
        raise HTTPClientError(
            message=f"Invalid URL format: {url}",
            error_code="INVALID_URL",
        )

    except httpx.HTTPError as exc:
        logger.error("Unexpected HTTP error for URL '%s': %s", url, str(exc))
        raise HTTPClientError(
            message=f"HTTP error while fetching '{url}': {str(exc)}",
            error_code="HTTP_ERROR",
        )

    except Exception as exc:
        logger.error(
            "Unexpected error while fetching URL '%s': %s",
            url,
            str(exc),
            exc_info=True,
        )
        raise HTTPClientError(
            message=f"Unexpected error while fetching '{url}': {str(exc)}",
            error_code="UNEXPECTED_ERROR",
        )