"""
Metadata service — core business logic layer.

Orchestrates the flow between the HTTP client and the database repository.
This module contains no knowledge of the API transport layer (FastAPI)
and no direct database driver calls, maintaining a clean separation of concerns.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.repositories import (
    find_metadata_by_url,
    insert_metadata,
)
from app.services.http_client import (
    fetch_url_metadata,
    HTTPClientError,
)
from app.models.metadata import MetadataStatus

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent storage and lookup.

    Strips trailing slashes and converts to lowercase scheme/host
    to prevent duplicate entries for effectively identical URLs.

    Args:
        url: The raw URL string.

    Returns:
        A normalized URL string.
    """
    normalized = str(url).rstrip("/")
    return normalized


async def collect_and_store_metadata(url: str) -> dict[str, Any]:
    """
    Collect metadata from a URL and store it in the database.

    This is the primary workflow for the POST endpoint. It performs
    a synchronous (within the request) fetch of URL metadata and
    persists the results to MongoDB.

    Args:
        url: The target URL to collect metadata from.

    Returns:
        The complete metadata record as stored in the database.

    Raises:
        HTTPClientError: If the URL cannot be fetched.
        PyMongoError: If the database operation fails.
    """
    normalized_url = _normalize_url(url)
    now = datetime.now(timezone.utc).isoformat()

    logger.info("Collecting metadata for URL: %s", normalized_url)

    # Fetch metadata from the target URL
    fetched_data = await fetch_url_metadata(normalized_url)

    # Build the complete metadata record
    metadata_record = {
        "url": normalized_url,
        "status_code": fetched_data["status_code"],
        "headers": fetched_data["headers"],
        "cookies": fetched_data["cookies"],
        "page_source": fetched_data["page_source"],
        "content_length": fetched_data["content_length"],
        "status": MetadataStatus.COMPLETED.value,
        "created_at": now,
        "updated_at": now,
    }

    # Persist to MongoDB (upsert)
    await insert_metadata(metadata_record)

    logger.info("Metadata collected and stored for URL: %s", normalized_url)
    return metadata_record


async def get_metadata(url: str) -> dict[str, Any] | None:
    """
    Retrieve metadata for a URL from the database.

    Performs a lookup in MongoDB for the given URL.
    Returns the full metadata record if found, or None if absent.

    Args:
        url: The target URL to look up.

    Returns:
        The metadata document if found, otherwise None.
    """
    normalized_url = _normalize_url(url)

    logger.info("Looking up metadata for URL: %s", normalized_url)

    record = await find_metadata_by_url(normalized_url)

    if record:
        logger.info("Cache HIT for URL: %s", normalized_url)
    else:
        logger.info("Cache MISS for URL: %s", normalized_url)

    return record


async def collect_metadata_background(url: str) -> None:
    """
    Background task to collect and store metadata for a URL.

    This function is designed to be called as an async background task
    (via asyncio.create_task) when a GET request encounters a cache miss.
    It runs independently of the request-response cycle.

    Errors are caught and logged rather than propagated, since there is
    no caller waiting for the result.

    Args:
        url: The target URL to collect metadata for.
    """
    normalized_url = _normalize_url(url)

    logger.info(
        "Background collection started for URL: %s", normalized_url
    )

    try:
        await collect_and_store_metadata(normalized_url)
        logger.info(
            "Background collection completed successfully for URL: %s",
            normalized_url,
        )

    except HTTPClientError as exc:
        logger.error(
            "Background collection failed for URL '%s': %s (code: %s)",
            normalized_url,
            exc.message,
            exc.error_code,
        )
        # Store a failed record so we don't endlessly retry on every GET
        await _store_failed_record(normalized_url, exc.message)

    except Exception as exc:
        logger.error(
            "Unexpected error in background collection for URL '%s': %s",
            normalized_url,
            str(exc),
            exc_info=True,
        )
        await _store_failed_record(normalized_url, str(exc))


async def _store_failed_record(url: str, error_message: str) -> None:
    """
    Store a failed metadata record in the database.

    This prevents infinite background retries for URLs that consistently
    fail. Subsequent GET requests will see the failed status and can
    decide whether to retry.

    Args:
        url: The URL that failed to be collected.
        error_message: Description of the failure.
    """
    now = datetime.now(timezone.utc).isoformat()

    failed_record = {
        "url": url,
        "status_code": 0,
        "headers": {},
        "cookies": [],
        "page_source": "",
        "content_length": 0,
        "status": MetadataStatus.FAILED.value,
        "error_message": error_message,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await insert_metadata(failed_record)
        logger.info("Failed record stored for URL: %s", url)
    except Exception as exc:
        # Last resort — just log. We cannot block on this.
        logger.error(
            "Could not store failed record for URL '%s': %s",
            url,
            str(exc),
        )