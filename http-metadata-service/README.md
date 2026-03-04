# HTTP Metadata Inventory Service

A FastAPI-based microservice for collecting, storing, and retrieving HTTP metadata (headers, cookies, and page source) for given URLs. Built with async Python, MongoDB, and Docker.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Environment Variables](#environment-variables)
- [API Documentation](#api-documentation)
  - [Endpoints](#endpoints)
  - [POST /api/v1/metadata/](#post-apiv1metadata)
  - [GET /api/v1/metadata/](#get-apiv1metadata)
  - [GET /health](#get-health)
- [Background Worker](#background-worker)
- [Testing](#testing)
  - [Running Tests](#running-tests)
  - [Test Coverage](#test-coverage)
- [Design Decisions](#design-decisions)
- [Future Improvements](#future-improvements)

---

## Overview

This service provides a simple HTTP metadata inventory system that:

1. **Collects** HTTP headers, cookies, and page source from any given URL.
2. **Stores** the collected metadata in MongoDB for fast retrieval.
3. **Serves** cached metadata instantly, or triggers asynchronous background collection on cache misses.

### Key Features

- **Synchronous Collection (POST):** Fetch and store metadata in a single request.
- **Smart Retrieval (GET):** Instant cache hits with automatic background collection for misses.
- **Background Workers:** Non-blocking async tasks via `asyncio.create_task()` — no external HTTP self-calls or polling loops.
- **Task Deduplication:** Prevents redundant concurrent fetches for the same URL.
- **Failed Record Tracking:** Stores failure records to prevent infinite retry loops.
- **System Resilience:** Retry logic for MongoDB connections, graceful error handling throughout.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Application                         │
│                                                               │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │   Routes     │───▶│   Services   │───▶│  Repository    │  │
│  │  (Transport) │    │  (Business   │    │  (Data Access) │  │
│  │              │    │   Logic)     │    │                │  │
│  └─────────────┘    └──────┬───────┘    └───────┬────────┘  │
│                            │                     │           │
│                     ┌──────▼───────┐             │           │
│                     │  HTTP Client │             │           │
│                     │  (httpx)     │             │           │
│                     └──────────────┘             │           │
│                                                  │           │
│  ┌─────────────────────┐                         │           │
│  │  Background Worker   │─────────────────────────┘          │
│  │  (asyncio.create_    │                                    │
│  │   task)              │                                    │
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │     MongoDB      │
                  │  (Document DB)   │
                  └─────────────────┘
```

### Request Flow

#### POST `/api/v1/metadata/`
```
Client ──POST──▶ Route ──▶ Service ──▶ HTTP Client ──▶ Target URL
                                  │
                                  ▼
                              Repository ──▶ MongoDB
                                  │
                                  ▼
Client ◀──201──── Route ◀── Full Metadata Record
```

#### GET `/api/v1/metadata/?url=...` (Cache Hit)
```
Client ──GET──▶ Route ──▶ Service ──▶ Repository ──▶ MongoDB
                                          │
                                          ▼
Client ◀──200──── Route ◀──────── Full Metadata Record
```

#### GET `/api/v1/metadata/?url=...` (Cache Miss)
```
Client ──GET──▶ Route ──▶ Service ──▶ Repository ──▶ MongoDB (not found)
                  │                        
                  ├──▶ Schedule Background Task ──▶ asyncio.create_task()
                  │                                      │
Client ◀──202──── │                                      ▼
                  │                              HTTP Client ──▶ Target URL
                  │                                      │
                  │                              Repository ──▶ MongoDB (stored)
                  │                                      
                  │    (Available for future GET requests)
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11+ | Core logic and scripting |
| Web Framework | FastAPI | API development with auto-generated docs |
| Database | MongoDB 7.0 | Document storage for metadata |
| Async HTTP | httpx | Non-blocking outbound HTTP requests |
| MongoDB Driver | motor | Async MongoDB driver |
| Validation | Pydantic v2 | Request/response schema validation |
| Configuration | pydantic-settings | Type-safe environment variable management |
| Orchestration | Docker Compose | Local development and isolation |
| Testing | pytest + pytest-asyncio | Unit and integration testing |
| ASGI Server | Uvicorn | High-performance async server |

---

## Project Structure

```
http-metadata-service/
│
├── docker-compose.yml          # Full stack orchestration (API + MongoDB)
├── Dockerfile                  # Multi-stage build for the API service
├── requirements.txt            # Python dependencies (pinned versions)
├── pytest.ini                  # Pytest configuration
├── .env                        # Environment variables (local dev)
├── .env.example                # Environment variable template
├── .gitignore                  # Git exclusions
├── .dockerignore               # Docker build exclusions
├── README.md                   # This file
│
├── app/                        # Application source code
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point + lifespan
│   ├── config.py               # Settings via pydantic-settings
│   │
│   ├── models/                 # Pydantic schemas (request/response)
│   │   ├── __init__.py
│   │   └── metadata.py
│   │
│   ├── routes/                 # API endpoints (transport layer)
│   │   ├── __init__.py
│   │   └── metadata.py
│   │
│   ├── services/               # Business logic layer
│   │   ├── __init__.py
│   │   ├── metadata_service.py # Core orchestration logic
│   │   └── http_client.py      # Async HTTP fetching
│   │
│   ├── db/                     # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py       # MongoDB connection management
│   │   └── repositories.py     # CRUD operations
│   │
│   └── workers/                # Background task management
│       ├── __init__.py
│       └── collector.py        # Async task scheduling + deduplication
│
└── tests/                      # Test suite
    ├── __init__.py
    ├── conftest.py             # Shared fixtures
    ├── test_models.py          # Pydantic model validation tests
    ├── test_http_client.py     # HTTP client tests
    ├── test_metadata_service.py # Service layer tests
    ├── test_workers.py         # Background worker tests
    ├── test_post_metadata.py   # POST endpoint tests
    ├── test_get_metadata.py    # GET endpoint tests
    └── test_health.py          # Health/root endpoint tests
```

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)

That's it! Everything else runs inside containers.

### Quick Start

**1. Clone the repository:**

```bash
git clone https://github.com/vipinbansal179/CloudSEK_Assignment.git
cd http-metadata-service
```

**2. Start the service:**

```bash
docker-compose up --build
```

This will:
- Build the FastAPI application image
- Pull and start MongoDB 7.0
- Wait for MongoDB to be healthy before starting the API
- Create database indexes automatically
- Start the API server on port 8000

**3. Verify the service is running:**

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "service": "HTTP Metadata Inventory Service",
#   "version": "1.0.0",
#   "active_background_tasks": 0
# }
```

**4. Open the interactive API documentation:**

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

**5. Stop the service:**

```bash
# Stop containers
docker-compose down

# Stop and remove all data (including MongoDB volume)
docker-compose down -v
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | HTTP Metadata Inventory Service | Display name |
| `APP_VERSION` | 1.0.0 | Application version |
| `DEBUG` | false | Enable debug mode |
| `MONGO_URL` | mongodb://mongodb:27017 | MongoDB connection string |
| `MONGO_DB_NAME` | metadata_inventory | Database name |
| `HTTP_REQUEST_TIMEOUT` | 30.0 | HTTP request timeout (seconds) |
| `HTTP_MAX_REDIRECTS` | 10 | Maximum HTTP redirects |
| `HTTP_USER_AGENT` | HTTPMetadataInventoryService/1.0 | User-Agent header |

Copy `.env.example` to `.env` and modify as needed:

```bash
cp .env.example .env
```

---

## API Documentation

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/metadata/` | Create a metadata record for a URL |
| `GET` | `/api/v1/metadata/?url=<url>` | Retrieve metadata for a URL |
| `GET` | `/health` | Service health check |
| `GET` | `/` | Service information |
| `GET` | `/docs` | Swagger UI (interactive docs) |
| `GET` | `/redoc` | ReDoc documentation |

---

### POST `/api/v1/metadata/`

Create a metadata record by fetching headers, cookies, and page source from a URL.

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/metadata/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Success Response (201 Created):**

```json
{
  "url": "https://example.com",
  "status": "completed",
  "message": "Metadata successfully collected and stored.",
  "data": {
    "url": "https://example.com",
    "status_code": 200,
    "headers": {
      "content-type": "text/html; charset=UTF-8",
      "server": "ECS (dcb/7F84)",
      "content-length": "1256",
      "cache-control": "max-age=604800"
    },
    "cookies": [],
    "page_source": "<!doctype html>\n<html>\n<head>\n    <title>Example Domain</title>...",
    "content_length": 1256,
    "status": "completed",
    "created_at": "2024-01-15T10:30:00+00:00",
    "updated_at": "2024-01-15T10:30:00+00:00"
  }
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 422 | Invalid URL format or missing field |
| 502 | Target URL is unreachable |
| 504 | Request to target URL timed out |
| 500 | Unexpected server error |

---

### GET `/api/v1/metadata/?url=<url>`

Retrieve stored metadata for a URL. If not found, triggers background collection.

**Request:**

```bash
curl "http://localhost:8000/api/v1/metadata/?url=https://example.com"
```

**Cache Hit Response (200 OK):**

```json
{
  "url": "https://example.com",
  "status_code": 200,
  "headers": {
    "content-type": "text/html; charset=UTF-8"
  },
  "cookies": [],
  "page_source": "<!doctype html>...",
  "content_length": 1256,
  "status": "completed",
  "created_at": "2024-01-15T10:30:00+00:00",
  "updated_at": "2024-01-15T10:30:00+00:00"
}
```

**Cache Miss Response (202 Accepted):**

```json
{
  "url": "https://example.com",
  "status": "pending",
  "message": "Metadata collection has been initiated. Please retry shortly."
}
```

**Workflow:**

1. Service checks MongoDB for existing metadata.
2. **If found:** Returns full metadata immediately (200 OK).
3. **If not found:** Returns 202 Accepted and fires an async background task to collect the metadata.
4. **On retry:** The next GET request will find the data and return 200 OK.

```bash
# First request — cache miss, triggers background collection
curl "http://localhost:8000/api/v1/metadata/?url=https://httpbin.org/get"
# Response: 202 — "Metadata collection has been initiated..."

# Wait a moment, then retry — cache hit
curl "http://localhost:8000/api/v1/metadata/?url=https://httpbin.org/get"
# Response: 200 — Full metadata returned
```

---

### GET `/health`

Service health check endpoint.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "service": "HTTP Metadata Inventory Service",
  "version": "1.0.0",
  "active_background_tasks": 0
}
```

---

## Background Worker

The service implements an internal async background worker for metadata collection:

### How It Works

1. A `GET` request encounters a **cache miss** (URL not in MongoDB).
2. The endpoint calls `schedule_background_collection(url)`.
3. The worker creates an `asyncio.create_task()` — an internal async task.
4. The API responds immediately with **202 Accepted**.
5. The background task fetches metadata and stores it in MongoDB.
6. Subsequent `GET` requests find the cached data.

### Key Design Decisions

| Feature | Implementation | Reason |
|---------|---------------|--------|
| Task execution | `asyncio.create_task()` | Internal orchestration, no external calls |
| Deduplication | In-memory task registry with `asyncio.Lock` | Prevents redundant concurrent fetches |
| Error handling | Catches all errors, stores failed records | Prevents infinite retry loops |
| Cleanup | Automatic removal of completed tasks | Prevents memory leaks |
| Shutdown | `cancel_all_tasks()` on app shutdown | Graceful resource cleanup |

---

## Testing

### Running Tests

**Option 1: Run tests inside Docker (recommended):**

```bash
# Build and run tests
docker-compose run --rm api python -m pytest

# With verbose output
docker-compose run --rm api python -m pytest -v

# Run specific test file
docker-compose run --rm api python -m pytest tests/test_post_metadata.py

# Run specific test class
docker-compose run --rm api python -m pytest tests/test_get_metadata.py::TestGetMetadataCacheHit
```

**Option 2: Run tests locally (requires Python 3.11+):**

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in your browser
```

### Test Coverage

The test suite covers:

| Module | Tests | Coverage Areas |
|--------|-------|---------------|
| `test_models.py` | 12 | URL validation, schema defaults, enum values, rejection of invalid input |
| `test_http_client.py` | 10 | Successful fetch, timeouts, connection errors, redirects, header/cookie extraction |
| `test_metadata_service.py` | 8 | Collect workflow, cache hit/miss, background error handling, URL normalization |
| `test_workers.py` | 7 | Task scheduling, deduplication, monitoring, cleanup, cancellation |
| `test_post_metadata.py` | 7 | 201/422/500/502/504 responses, valid/invalid input |
| `test_get_metadata.py` | 7 | 200/202/422/500 responses, cache hit/miss, failed record re-collection |
| `test_health.py` | 4 | Health check, active tasks, root endpoint, documentation links |

**Total: 55+ test cases**

---

## Design Decisions

### 1. Separation of Concerns

```
Routes (Transport) → Services (Business Logic) → Repository (Data Access)
```

Each layer has a single responsibility:
- **Routes:** HTTP concerns only (status codes, request parsing, response formatting)
- **Services:** Core logic (orchestration, URL normalization, error handling)
- **Repository:** Database operations only (CRUD, indexing)

### 2. Async-First Architecture

- `httpx.AsyncClient` for non-blocking HTTP requests
- `motor` for async MongoDB operations
- `asyncio.create_task()` for background workers
- All I/O-bound operations are awaited, never blocking the event loop

### 3. URL Normalization

URLs are normalized (trailing slashes stripped) before storage and lookup to prevent duplicate records for effectively identical URLs.

### 4. Failed Record Tracking

When background collection fails, a "failed" record is stored in MongoDB. This prevents:
- Infinite retry loops on every GET request
- Resource waste on consistently unreachable URLs

Failed records trigger a re-collection attempt on the next GET request.

### 5. Docker Multi-Stage Build

The Dockerfile uses a two-stage build:
- **Builder stage:** Installs dependencies in a virtual environment
- **Runtime stage:** Copies only the venv + source code, runs as non-root user

Result: ~150MB image instead of ~800MB.

### 6. MongoDB Health-Based Dependency

Docker Compose uses `depends_on` with `condition: service_healthy` to ensure MongoDB is actually ready (not just started) before the API begins accepting requests.

---

## Future Improvements

- [ ] **Redis caching layer** — Add Redis for faster lookups before hitting MongoDB
- [ ] **Celery/RabbitMQ** — Replace `asyncio.create_task()` with a distributed task queue for horizontal scaling
- [ ] **Rate limiting** — Prevent abuse with per-IP or per-URL rate limits
- [ ] **TTL-based cache invalidation** — Auto-expire metadata records after a configurable duration
- [ ] **Webhook notifications** — Notify clients when background collection completes
- [ ] **Bulk URL submission** — Accept multiple URLs in a single POST request
- [ ] **Authentication** — API key or JWT-based access control
- [ ] **Prometheus metrics** — Export request counts, latencies, and task metrics
- [ ] **JavaScript rendering** — Optional headless browser support for SPA metadata

---

## License

This project is created as part of a hiring challenge assessment.