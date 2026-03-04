"""
Database package.

Provides MongoDB connection management and data access repositories.
"""

from app.db.connection import (
    connect_to_mongodb,
    close_mongodb_connection,
    get_database,
)

__all__ = [
    "connect_to_mongodb",
    "close_mongodb_connection",
    "get_database",
]