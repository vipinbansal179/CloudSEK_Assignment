"""
Pytest configuration and shared fixtures.

Provides reusable test fixtures including:
- FastAPI test client with mocked MongoDB
- Sample metadata records
- Mocked HTTP responses
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.config import Settings
from app.main import app


# ---------------------------------------------------------------------------
# Event Loop Configuration
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create a session-scoped event loop for async tests.
    
    Overrides the default function-scoped loop to allow
    session-scoped async fixtures.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Test Settings
# ---------------------------------------------------------------------------

@pytest.fixture
def test_settings() -> Settings:
    """Provide test-specific application settings."""
    return Settings(
        app_name="Test Metadata Service",
        app_version="0.0.1-test",
        debug=True,
        mongo_url="mongodb://localhost:27017",
        mongo_db_name="test_metadata_inventory",
        http_request_timeout=10.0,
        http_max_redirects=5,
        http_user_agent="TestAgent/1.0",
    )


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_url() -> str:
    """Provide a sample URL for testing."""
    return "https://example.com"


@pytest.fixture
def sample_headers() -> dict[str, str]:
    """Provide sample HTTP response headers."""
    return {
        "content-type": "text/html; charset=UTF-8",
        "content-length": "1256",
        "server": "ECS (dcb/7F84)",
        "cache-control": "max-age=604800",
        "date": "Mon, 15 Jan 2024 10:30:00 GMT",
        "etag": '"3147526947"',
    }


@pytest.fixture
def sample_cookies() -> list[dict[str, str]]:
    """Provide sample cookie data."""
    return [
        {
            "name": "session_id",
            "value": "abc123def456",
            "domain": "example.com",
            "path": "/",
        },
        {
            "name": "tracking",
            "value": "xyz789",
            "domain": ".example.com",
            "path": "/",
        },
    ]


@pytest.fixture
def sample_page_source() -> str:
    """Provide sample HTML page source."""
    return """<!doctype html>
<html>
<head>
    <title>Example Domain</title>
    <meta charset="utf-8" />
</head>
<body>
    <h1>Example Domain</h1>
    <p>This domain is for use in illustrative examples.</p>
</body>
</html>"""


@pytest.fixture
def sample_metadata_record(
    sample_url: str,
    sample_headers: dict[str, str],
    sample_cookies: list[dict[str, str]],
    sample_page_source: str,
) -> dict[str, Any]:
    """Provide a complete sample metadata record as stored in MongoDB."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "url": sample_url,
        "status_code": 200,
        "headers": sample_headers,
        "cookies": sample_cookies,
        "page_source": sample_page_source,
        "content_length": len(sample_page_source.encode("utf-8")),
        "status": "completed",
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture
def sample_failed_record(sample_url: str) -> dict[str, Any]:
    """Provide a sample failed metadata record."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "url": sample_url,
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


@pytest.fixture
def sample_fetched_data(
    sample_headers: dict[str, str],
    sample_cookies: list[dict[str, str]],
    sample_page_source: str,
) -> dict[str, Any]:
    """Provide sample data as returned by the HTTP client fetch function."""
    return {
        "status_code": 200,
        "headers": sample_headers,
        "cookies": sample_cookies,
        "page_source": sample_page_source,
        "content_length": len(sample_page_source.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# API Test Client Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_connection():
    """
    Mock the MongoDB connection for testing.
    
    Patches both connect and disconnect functions so tests
    don't require a running MongoDB instance.
    """
    with patch("app.main.connect_to_mongodb", new_callable=AsyncMock) as mock_connect, \
         patch("app.main.close_mongodb_connection", new_callable=AsyncMock) as mock_close, \
         patch("app.main.ensure_indexes", new_callable=AsyncMock) as mock_indexes:
        yield {
            "connect": mock_connect,
            "close": mock_close,
            "indexes": mock_indexes,
        }


@pytest_asyncio.fixture
async def async_client(mock_db_connection) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP test client for the FastAPI application.
    
    Uses httpx.AsyncClient with ASGITransport to make requests
    directly to the app without starting a server.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def sync_client(mock_db_connection) -> Generator[TestClient, None, None]:
    """
    Provide a synchronous test client for simple endpoint tests.
    """
    with TestClient(app) as client:
        yield client