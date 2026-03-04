"""
Metadata API endpoints.

Defines the POST and GET endpoints for the HTTP Metadata Inventory Service.
This module handles HTTP-specific concerns (status codes, response models,
query parameters) and delegates all business logic to the services layer.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import HttpUrl

from app.models.metadata import (
    MetadataCreateRequest,
    MetadataCreatedResponse,
    MetadataResponse,
    MetadataAcceptedResponse,
    MetadataStatus,
    ErrorResponse,
)
from app.services.metadata_service import (
    collect_and_store_metadata,
    get_metadata,
)
from app.services.http_client import (
    HTTPClientError,
    URLUnreachableError,
    RequestTimeoutError,
)
from app.workers.collector import (
    schedule_background_collection,
    is_url_being_collected,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["Metadata"])


@router.post(
    "/",
    response_model=MetadataCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create metadata record for a URL",
    description=(
        "Fetches HTTP headers, cookies, and page source from the provided URL "
        "and stores the collected metadata in the database."
    ),
    responses={
        201: {
            "description": "Metadata successfully collected and stored.",
            "model": MetadataCreatedResponse,
        },
        400: {
            "description": "Invalid URL or request format.",
            "model": ErrorResponse,
        },
        502: {
            "description": "Target URL is unreachable.",
            "model": ErrorResponse,
        },
        504: {
            "description": "Request to target URL timed out.",
            "model": ErrorResponse,
        },
    },
)
async def create_metadata(request: MetadataCreateRequest) -> MetadataCreatedResponse:
    """
    POST /metadata/

    Collect metadata from the given URL and store it in MongoDB.
    This endpoint performs the fetch synchronously within the request
    and returns the full metadata record upon completion.

    Args:
        request: Request body containing the target URL.

    Returns:
        MetadataCreatedResponse with the full metadata record.
    """
    url = str(request.url)

    try:
        record = await collect_and_store_metadata(url)

        return MetadataCreatedResponse(
            url=record["url"],
            status=MetadataStatus.COMPLETED,
            message="Metadata successfully collected and stored.",
            data=MetadataResponse(**record),
        )

    except RequestTimeoutError as exc:
        logger.warning("Timeout creating metadata for URL '%s': %s", url, exc.message)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        )

    except URLUnreachableError as exc:
        logger.warning("URL unreachable '%s': %s", url, exc.message)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        )

    except HTTPClientError as exc:
        logger.error("HTTP client error for URL '%s': %s", url, exc.message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        )

    except Exception as exc:
        logger.error(
            "Unexpected error creating metadata for URL '%s': %s",
            url,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while collecting metadata.",
        )


@router.get(
    "/",
    summary="Retrieve metadata for a URL",
    description=(
        "Retrieves stored metadata for the given URL. If the record exists, "
        "returns the full dataset. If not, returns a 202 Accepted response "
        "and initiates background collection."
    ),
    responses={
        200: {
            "description": "Metadata record found and returned.",
            "model": MetadataResponse,
        },
        202: {
            "description": "Metadata collection initiated in background.",
            "model": MetadataAcceptedResponse,
        },
        400: {
            "description": "Invalid URL format.",
            "model": ErrorResponse,
        },
    },
    # We handle multiple response models manually
    response_model=None,
)
async def get_metadata_endpoint(
    url: Annotated[
        HttpUrl,
        Query(
            description="The URL to retrieve metadata for.",
            examples=["https://example.com"],
        ),
    ],
) -> MetadataResponse | MetadataAcceptedResponse:
    """
    GET /metadata/?url=<target_url>

    Retrieve metadata for a given URL from the database.

    Workflow:
    1. Check if metadata exists in MongoDB.
    2. If found: return full metadata (200 OK).
    3. If not found: return 202 Accepted and trigger background collection.

    Args:
        url: Query parameter — the target URL to look up.

    Returns:
        MetadataResponse (200) if record exists.
        MetadataAcceptedResponse (202) if collection was triggered.
    """
    url_str = str(url)

    try:
        # Step 1: Inventory check
        record = await get_metadata(url_str)

        # Step 2: Immediate resolution — record exists
        if record is not None:
            # Check if the record is a previous failed attempt
            if record.get("status") == MetadataStatus.FAILED.value:
                # Re-trigger background collection for failed records
                await schedule_background_collection(url_str)

                return MetadataAcceptedResponse(
                    url=url_str,
                    status=MetadataStatus.PENDING,
                    message=(
                        "Previous collection attempt failed. "
                        "A new collection has been initiated. Please retry shortly."
                    ),
                )

            return MetadataResponse(**record)

        # Step 3: Conditional inventory update — cache miss
        already_collecting = await is_url_being_collected(url_str)

        if not already_collecting:
            await schedule_background_collection(url_str)

        message = (
            "Metadata collection is already in progress. Please retry shortly."
            if already_collecting
            else "Metadata collection has been initiated. Please retry shortly."
        )

        return MetadataAcceptedResponse(
            url=url_str,
            status=MetadataStatus.PENDING,
            message=message,
        )

    except Exception as exc:
        logger.error(
            "Unexpected error retrieving metadata for URL '%s': %s",
            url_str,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving metadata.",
        )