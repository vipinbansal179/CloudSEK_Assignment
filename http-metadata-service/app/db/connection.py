"""
MongoDB connection management.

Handles async MongoDB client lifecycle with retry logic
to ensure resilience during database startup delays.
"""

import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Module-level references for the MongoDB client and database.
# These are initialised during application startup.
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_to_mongodb(
    max_retries: int = 5,
    retry_delay: float = 3.0,
) -> None:
    """
    Establish a connection to MongoDB with retry logic.

    Implements exponential backoff to handle scenarios where the
    database container may not be ready immediately on startup.

    Args:
        max_retries: Maximum number of connection attempts.
        retry_delay: Initial delay (seconds) between retries.

    Raises:
        ConnectionFailure: If all retry attempts are exhausted.
    """
    global _client, _database
    settings = get_settings()

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Attempting MongoDB connection (attempt %d/%d)...",
                attempt,
                max_retries,
            )
            _client = AsyncIOMotorClient(
                settings.mongo_url,
                serverSelectionTimeoutMS=5000,
            )
            # Verify the connection is actually alive
            await _client.admin.command("ping")
            _database = _client[settings.mongo_db_name]

            logger.info(
                "Successfully connected to MongoDB at %s, database: %s",
                settings.mongo_url,
                settings.mongo_db_name,
            )
            return

        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            logger.warning(
                "MongoDB connection attempt %d/%d failed: %s",
                attempt,
                max_retries,
                str(exc),
            )
            if attempt == max_retries:
                logger.error(
                    "Could not connect to MongoDB after %d attempts.", max_retries
                )
                raise
            await asyncio.sleep(retry_delay * attempt)  # Exponential backoff


async def close_mongodb_connection() -> None:
    """
    Gracefully close the MongoDB client connection.
    
    Should be called during application shutdown to release resources.
    """
    global _client, _database

    if _client is not None:
        _client.close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """
    Retrieve the active MongoDB database instance.

    Returns:
        AsyncIOMotorDatabase: The active database instance.

    Raises:
        RuntimeError: If the database connection has not been initialised.
    """
    if _database is None:
        raise RuntimeError(
            "MongoDB connection is not initialised. "
            "Ensure 'connect_to_mongodb()' is called during application startup."
        )
    return _database