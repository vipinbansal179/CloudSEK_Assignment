"""
Background metadata collector.

Manages async background tasks for metadata collection triggered
by cache misses on the GET endpoint. Uses asyncio.create_task()
for internal orchestration — no external HTTP self-calls or polling loops.

This module also provides a simple in-memory task registry to prevent
duplicate background collections for the same URL running concurrently.
"""

import asyncio
import logging
from typing import Set

from app.services.metadata_service import collect_metadata_background

logger = logging.getLogger(__name__)

# In-memory set of URLs currently being processed in background.
# Prevents duplicate concurrent tasks for the same URL.
_active_tasks: dict[str, asyncio.Task] = {}

# Lock to ensure thread-safe access to _active_tasks
_tasks_lock: asyncio.Lock = asyncio.Lock()


async def schedule_background_collection(url: str) -> bool:
    """
    Schedule a background metadata collection task for a URL.

    This function is called by the GET endpoint when a cache miss occurs.
    It ensures that only one background task runs per URL at any given time,
    preventing redundant work when multiple GET requests hit the same
    uncached URL simultaneously.

    The task runs independently of the request-response cycle via
    asyncio.create_task(), satisfying the architectural constraint
    of internal logic orchestration without external HTTP self-calls.

    Args:
        url: The target URL to collect metadata for.

    Returns:
        True if a new task was scheduled, False if a task for this URL
        is already in progress.
    """
    async with _tasks_lock:
        # Clean up completed tasks before checking
        _cleanup_completed_tasks()

        if url in _active_tasks:
            task = _active_tasks[url]
            if not task.done():
                logger.info(
                    "Background collection already in progress for URL: %s",
                    url,
                )
                return False

        # Create a new background task
        task = asyncio.create_task(
            _run_collection(url),
            name=f"metadata_collection_{url}",
        )

        _active_tasks[url] = task

        logger.info(
            "Background collection task scheduled for URL: %s (active tasks: %d)",
            url,
            len(_active_tasks),
        )

        return True


async def _run_collection(url: str) -> None:
    """
    Internal wrapper that runs the metadata collection and handles cleanup.

    This is the actual coroutine that gets scheduled via asyncio.create_task().
    It delegates the real work to the service layer and ensures proper
    cleanup of the task registry upon completion.

    Args:
        url: The target URL to collect metadata for.
    """
    try:
        await collect_metadata_background(url)
    finally:
        # Ensure cleanup happens regardless of success or failure
        async with _tasks_lock:
            _active_tasks.pop(url, None)
            logger.debug(
                "Background task cleaned up for URL: %s (remaining: %d)",
                url,
                len(_active_tasks),
            )


def _cleanup_completed_tasks() -> None:
    """
    Remove completed or cancelled tasks from the active registry.

    Called before scheduling a new task to prevent unbounded
    memory growth from accumulated finished task references.
    This function must be called while holding _tasks_lock.
    """
    completed_urls = [
        url for url, task in _active_tasks.items() if task.done()
    ]

    for url in completed_urls:
        _active_tasks.pop(url, None)

    if completed_urls:
        logger.debug(
            "Cleaned up %d completed background tasks.",
            len(completed_urls),
        )


async def get_active_task_count() -> int:
    """
    Return the number of currently active background tasks.

    Useful for health checks and monitoring.

    Returns:
        Number of active background collection tasks.
    """
    async with _tasks_lock:
        _cleanup_completed_tasks()
        return len(_active_tasks)


async def is_url_being_collected(url: str) -> bool:
    """
    Check if a URL is currently being collected in the background.

    Useful for the GET endpoint to provide more specific messaging
    to the user about whether collection is already in progress.

    Args:
        url: The URL to check.

    Returns:
        True if a background task is actively collecting this URL.
    """
    async with _tasks_lock:
        if url in _active_tasks:
            return not _active_tasks[url].done()
        return False


async def cancel_all_tasks() -> int:
    """
    Cancel all active background tasks.

    Called during application shutdown to ensure graceful cleanup
    of all in-flight background operations.

    Returns:
        Number of tasks that were cancelled.
    """
    async with _tasks_lock:
        cancelled_count = 0

        for url, task in _active_tasks.items():
            if not task.done():
                task.cancel()
                cancelled_count += 1
                logger.info("Cancelled background task for URL: %s", url)

        _active_tasks.clear()

        logger.info(
            "All background tasks cancelled. Total cancelled: %d",
            cancelled_count,
        )

        return cancelled_count