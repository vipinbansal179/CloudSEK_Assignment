"""
Metadata repository for MongoDB CRUD operations.

Encapsulates all direct database interactions for the metadata collection,
keeping the data access layer separate from business logic.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
from pymongo.errors import PyMongoError

from app.db.connection import get_database

logger = logging.getLogger(__name__)

COLLECTION_NAME = "metadata"


async def ensure_indexes() -> None:
    """
    Create necessary indexes on the metadata collection.

    Ensures a unique index on the 'url' field for fast lookups
    and to prevent duplicate records for the same URL.
    """
    db: AsyncIOMotorDatabase = get_database()
    collection = db[COLLECTION_NAME]

    indexes = [
        IndexModel([("url", ASCENDING)], unique=True, name="idx_url_unique"),
    ]

    try:
        await collection.create_indexes(indexes)
        logger.info("Database indexes ensured on '%s' collection.", COLLECTION_NAME)
    except PyMongoError as exc:
        logger.error("Failed to create indexes: %s", str(exc))
        raise


async def find_metadata_by_url(url: str) -> dict[str, Any] | None:
    """
    Retrieve a metadata record by its URL.

    Args:
        url: The normalised URL to look up.

    Returns:
        The metadata document if found, otherwise None.
    """
    db: AsyncIOMotorDatabase = get_database()
    collection = db[COLLECTION_NAME]

    try:
        document = await collection.find_one(
            {"url": url},
            {"_id": 0},  # Exclude MongoDB internal _id from results
        )
        return document
    except PyMongoError as exc:
        logger.error("Database error during lookup for URL '%s': %s", url, str(exc))
        raise


async def insert_metadata(data: dict[str, Any]) -> str:
    """
    Insert a new metadata record into the collection.

    If a record with the same URL already exists, it will be
    replaced (upsert) to ensure data freshness.

    Args:
        data: The metadata document to insert.

    Returns:
        The URL of the upserted record.
    """
    db: AsyncIOMotorDatabase = get_database()
    collection = db[COLLECTION_NAME]

    try:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        result = await collection.update_one(
            {"url": data["url"]},
            {"$set": data},
            upsert=True,
        )

        action = "inserted" if result.upserted_id else "updated"
        logger.info("Metadata %s for URL: %s", action, data["url"])

        return data["url"]

    except PyMongoError as exc:
        logger.error(
            "Database error during upsert for URL '%s': %s", data["url"], str(exc)
        )
        raise


async def delete_metadata_by_url(url: str) -> bool:
    """
    Delete a metadata record by its URL.

    Args:
        url: The URL whose record should be deleted.

    Returns:
        True if a record was deleted, False if no record was found.
    """
    db: AsyncIOMotorDatabase = get_database()
    collection = db[COLLECTION_NAME]

    try:
        result = await collection.delete_one({"url": url})
        deleted = result.deleted_count > 0

        if deleted:
            logger.info("Metadata deleted for URL: %s", url)
        else:
            logger.info("No metadata found to delete for URL: %s", url)

        return deleted

    except PyMongoError as exc:
        logger.error(
            "Database error during delete for URL '%s': %s", url, str(exc)
        )
        raise