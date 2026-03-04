"""
FastAPI application entry point.

Configures the application, registers lifecycle events,
includes route modules, and sets up logging.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.connection import connect_to_mongodb, close_mongodb_connection
from app.db.repositories import ensure_indexes
from app.routes.metadata import router as metadata_router
from app.workers.collector import cancel_all_tasks, get_active_task_count

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Connect to MongoDB, ensure indexes.
    - Shutdown: Cancel background tasks, close DB connection.
    """
    # --- Startup ---
    logger.info("Starting HTTP Metadata Inventory Service...")

    try:
        await connect_to_mongodb()
        await ensure_indexes()
        logger.info("Application startup complete.")
    except Exception as exc:
        logger.error("Failed to initialize application: %s", str(exc))
        raise

    yield

    # --- Shutdown ---
    logger.info("Shutting down HTTP Metadata Inventory Service...")

    cancelled = await cancel_all_tasks()
    if cancelled > 0:
        logger.info("Cancelled %d background tasks during shutdown.", cancelled)

    await close_mongodb_connection()
    logger.info("Application shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI Application Instance
# ---------------------------------------------------------------------------

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A service for collecting and inventorying HTTP metadata "
        "(headers, cookies, and page source) for given URLs. "
        "Supports synchronous collection via POST and asynchronous "
        "background collection triggered by GET cache misses."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(metadata_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health Check Endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    tags=["Health"],
    summary="Health check endpoint",
    description="Returns the current health status of the service.",
)
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns service status and active background task count.
    Useful for container orchestration and monitoring.
    """
    active_tasks = await get_active_task_count()

    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "active_background_tasks": active_tasks,
    }


# ---------------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/",
    tags=["Root"],
    summary="Service information",
    description="Returns basic information about the service.",
)
async def root() -> dict:
    """Root endpoint returning service information and documentation links."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_spec": "/openapi.json",
        },
        "endpoints": {
            "create_metadata": "POST /api/v1/metadata/",
            "get_metadata": "GET /api/v1/metadata/?url=<target_url>",
            "health": "GET /health",
        },
    }