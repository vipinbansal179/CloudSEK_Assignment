"""
Pydantic models for the metadata domain.

Defines request/response schemas and internal data transfer objects
with strict validation rules. Separates API contract (transport layer)
from internal data representation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MetadataStatus(str, Enum):
    """
    Status of a metadata record in the system.

    Attributes:
        PENDING: The metadata collection is in progress.
        COMPLETED: The metadata has been successfully collected and stored.
        FAILED: The metadata collection encountered an error.
    """
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class MetadataCreateRequest(BaseModel):
    """
    Schema for the POST endpoint request body.

    Validates that the provided input is a well-formed HTTP/HTTPS URL.

    Attributes:
        url: The target URL to collect metadata from.
    """
    url: HttpUrl = Field(
        ...,
        description="The target URL to collect metadata from (must be http or https).",
        examples=["https://example.com"],
    )

    @field_validator("url", mode="after")
    @classmethod
    def validate_url_scheme(cls, v: HttpUrl) -> HttpUrl:
        """Ensure only http and https schemes are accepted."""
        if v.scheme not in ("http", "https"):
            raise ValueError("URL scheme must be 'http' or 'https'.")
        return v


class MetadataGetRequest(BaseModel):
    """
    Schema for the GET endpoint query parameter.

    Attributes:
        url: The target URL whose metadata is being requested.
    """
    url: HttpUrl = Field(
        ...,
        description="The URL to retrieve metadata for.",
        examples=["https://example.com"],
    )


# ---------------------------------------------------------------------------
# Cookie Model
# ---------------------------------------------------------------------------

class CookieData(BaseModel):
    """
    Represents a single HTTP cookie.

    Attributes:
        name: The cookie name.
        value: The cookie value.
        domain: The domain the cookie belongs to.
        path: The path the cookie is scoped to.
    """
    name: str = Field(..., description="Cookie name.")
    value: str = Field(..., description="Cookie value.")
    domain: str = Field(default="", description="Cookie domain.")
    path: str = Field(default="/", description="Cookie path.")


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class MetadataResponse(BaseModel):
    """
    Full metadata response returned when a record exists in the database.

    Contains headers, cookies, page source, and metadata about the record itself.

    Attributes:
        url: The original URL that was fetched.
        status_code: The HTTP status code received from the target URL.
        headers: The HTTP response headers as key-value pairs.
        cookies: List of cookies received from the target URL.
        page_source: The raw HTML/text content of the page.
        content_length: Size of the page source in bytes.
        status: Current status of the metadata record.
        created_at: Timestamp when the record was first created.
        updated_at: Timestamp when the record was last updated.
    """
    url: str = Field(..., description="The original URL that was fetched.")
    status_code: int = Field(
        ...,
        description="HTTP status code from the target URL.",
        examples=[200],
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP response headers as key-value pairs.",
    )
    cookies: list[CookieData] = Field(
        default_factory=list,
        description="List of cookies received from the target URL.",
    )
    page_source: str = Field(
        default="",
        description="Raw HTML/text content of the page.",
    )
    content_length: int = Field(
        default=0,
        description="Size of the page source in bytes.",
    )
    status: MetadataStatus = Field(
        default=MetadataStatus.COMPLETED,
        description="Current status of the metadata record.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the record was created.",
    )
    updated_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the record was last updated.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "status_code": 200,
                "headers": {
                    "content-type": "text/html; charset=UTF-8",
                    "server": "ECS (dcb/7F84)",
                },
                "cookies": [
                    {
                        "name": "session_id",
                        "value": "abc123",
                        "domain": "example.com",
                        "path": "/",
                    }
                ],
                "page_source": "<!doctype html>...",
                "content_length": 1256,
                "status": "completed",
                "created_at": "2024-01-15T10:30:00+00:00",
                "updated_at": "2024-01-15T10:30:00+00:00",
            }
        }


class MetadataAcceptedResponse(BaseModel):
    """
    Response returned when a GET request triggers a background collection.

    Returned with HTTP 202 Accepted status to indicate the request
    has been acknowledged and metadata collection is in progress.

    Attributes:
        url: The URL whose metadata was requested.
        status: Will always be 'pending' for this response type.
        message: Human-readable message explaining the status.
    """
    url: str = Field(..., description="The URL whose metadata was requested.")
    status: MetadataStatus = Field(
        default=MetadataStatus.PENDING,
        description="Status indicating the record is being collected.",
    )
    message: str = Field(
        default="Metadata collection has been initiated. Please retry shortly.",
        description="Human-readable status message.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "status": "pending",
                "message": "Metadata collection has been initiated. Please retry shortly.",
            }
        }


class MetadataCreatedResponse(BaseModel):
    """
    Response returned after a successful POST request.

    Confirms that metadata has been collected and stored.

    Attributes:
        url: The URL that was processed.
        status: Status of the record (completed or failed).
        message: Human-readable confirmation message.
        data: The full metadata record if collection was successful.
    """
    url: str = Field(..., description="The URL that was processed.")
    status: MetadataStatus = Field(
        ...,
        description="Status of the metadata record.",
    )
    message: str = Field(
        ...,
        description="Human-readable status message.",
    )
    data: MetadataResponse | None = Field(
        default=None,
        description="Full metadata record if collection was successful.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "status": "completed",
                "message": "Metadata successfully collected and stored.",
                "data": {
                    "url": "https://example.com",
                    "status_code": 200,
                    "headers": {"content-type": "text/html"},
                    "cookies": [],
                    "page_source": "<!doctype html>...",
                    "content_length": 1256,
                    "status": "completed",
                    "created_at": "2024-01-15T10:30:00+00:00",
                    "updated_at": "2024-01-15T10:30:00+00:00",
                },
            }
        }


# ---------------------------------------------------------------------------
# Error Response Schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """
    Standardised error response schema.

    Attributes:
        detail: Human-readable error description.
        error_code: Machine-readable error identifier.
    """
    detail: str = Field(..., description="Human-readable error description.")
    error_code: str = Field(
        default="INTERNAL_ERROR",
        description="Machine-readable error code identifier.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "The provided URL is not reachable.",
                "error_code": "URL_UNREACHABLE",
            }
        }