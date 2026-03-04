"""
Tests for Pydantic models.

Validates request/response schema validation rules,
including URL validation, field defaults, and enum values.
"""

import pytest
from pydantic import ValidationError

from app.models.metadata import (
    MetadataCreateRequest,
    MetadataResponse,
    MetadataAcceptedResponse,
    MetadataCreatedResponse,
    MetadataStatus,
    CookieData,
    ErrorResponse,
)


class TestMetadataCreateRequest:
    """Tests for the POST request schema."""

    def test_valid_https_url(self) -> None:
        """Accept a valid HTTPS URL."""
        request = MetadataCreateRequest(url="https://example.com")
        assert str(request.url) == "https://example.com/"

    def test_valid_http_url(self) -> None:
        """Accept a valid HTTP URL."""
        request = MetadataCreateRequest(url="http://example.com")
        assert "http" in str(request.url)

    def test_valid_url_with_path(self) -> None:
        """Accept a URL with a path component."""
        request = MetadataCreateRequest(url="https://example.com/page/test")
        assert "example.com" in str(request.url)

    def test_invalid_url_format(self) -> None:
        """Reject a malformed URL string."""
        with pytest.raises(ValidationError) as exc_info:
            MetadataCreateRequest(url="not-a-url")
        assert "url" in str(exc_info.value).lower()

    def test_empty_url(self) -> None:
        """Reject an empty URL string."""
        with pytest.raises(ValidationError):
            MetadataCreateRequest(url="")

    def test_missing_url(self) -> None:
        """Reject a request with no URL field."""
        with pytest.raises(ValidationError):
            MetadataCreateRequest()

    def test_ftp_url_rejected(self) -> None:
        """Reject non-HTTP/HTTPS schemes like FTP."""
        with pytest.raises(ValidationError):
            MetadataCreateRequest(url="ftp://example.com")


class TestCookieData:
    """Tests for the cookie data model."""

    def test_full_cookie(self) -> None:
        """Create a cookie with all fields."""
        cookie = CookieData(
            name="session",
            value="abc123",
            domain="example.com",
            path="/app",
        )
        assert cookie.name == "session"
        assert cookie.value == "abc123"
        assert cookie.domain == "example.com"
        assert cookie.path == "/app"

    def test_cookie_defaults(self) -> None:
        """Verify default values for optional cookie fields."""
        cookie = CookieData(name="test", value="val")
        assert cookie.domain == ""
        assert cookie.path == "/"

    def test_cookie_missing_required(self) -> None:
        """Reject a cookie without required fields."""
        with pytest.raises(ValidationError):
            CookieData(name="test")


class TestMetadataStatus:
    """Tests for the metadata status enum."""

    def test_valid_statuses(self) -> None:
        """Verify all valid status values."""
        assert MetadataStatus.PENDING == "pending"
        assert MetadataStatus.COMPLETED == "completed"
        assert MetadataStatus.FAILED == "failed"

    def test_status_values(self) -> None:
        """Verify status enum has exactly three members."""
        assert len(MetadataStatus) == 3


class TestMetadataResponse:
    """Tests for the full metadata response model."""

    def test_valid_response(self, sample_metadata_record) -> None:
        """Create a valid metadata response from a complete record."""
        response = MetadataResponse(**sample_metadata_record)
        assert response.url == sample_metadata_record["url"]
        assert response.status_code == 200
        assert response.status == MetadataStatus.COMPLETED
        assert len(response.headers) > 0
        assert response.content_length > 0

    def test_response_missing_required_fields(self) -> None:
        """Reject a response missing required fields."""
        with pytest.raises(ValidationError):
            MetadataResponse(url="https://example.com")


class TestMetadataAcceptedResponse:
    """Tests for the 202 Accepted response model."""

    def test_default_values(self) -> None:
        """Verify default status and message."""
        response = MetadataAcceptedResponse(url="https://example.com")
        assert response.status == MetadataStatus.PENDING
        assert "retry" in response.message.lower()

    def test_custom_message(self) -> None:
        """Allow overriding the default message."""
        response = MetadataAcceptedResponse(
            url="https://example.com",
            message="Custom message for testing.",
        )
        assert response.message == "Custom message for testing."


class TestErrorResponse:
    """Tests for the error response model."""

    def test_error_response(self) -> None:
        """Create a valid error response."""
        error = ErrorResponse(detail="Something went wrong", error_code="TEST_ERROR")
        assert error.detail == "Something went wrong"
        assert error.error_code == "TEST_ERROR"

    def test_default_error_code(self) -> None:
        """Verify default error code."""
        error = ErrorResponse(detail="Error occurred")
        assert error.error_code == "INTERNAL_ERROR"


# Use conftest fixtures
@pytest.fixture
def sample_metadata_record() -> dict:
    """Inline fixture for model tests to avoid conftest dependency issues."""
    from datetime import datetime, timezone
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