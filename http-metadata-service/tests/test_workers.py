"""
Tests for the background worker/collector module.

Validates task scheduling, deduplication, cleanup, and
graceful cancellation of background collection tasks.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.workers.collector import (
    schedule_background_collection,
    get_active_task_count,
    is_url_being_collected,
    cancel_all_tasks,
    _active_tasks,
    _tasks_lock,
    _cleanup_completed_tasks,
)


@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """Ensure active tasks dict is clean before and after each test."""
    async with _tasks_lock:
        _active_tasks.clear()
    yield
    await cancel_all_tasks()


class TestScheduleBackgroundCollection:
    """Tests for task scheduling logic."""

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_schedule_new_task(self, mock_collect: AsyncMock) -> None:
        """Schedule a new background task for an uncached URL."""
        result = await schedule_background_collection("https://example.com")

        assert result is True

        # Give the event loop a chance to start the task
        await asyncio.sleep(0.1)

        mock_collect.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_prevent_duplicate_tasks(self, mock_collect: AsyncMock) -> None:
        """Prevent scheduling duplicate tasks for the same URL."""
        # Make the collection take some time
        mock_collect.side_effect = lambda url: asyncio.sleep(5)

        first_result = await schedule_background_collection("https://example.com")
        second_result = await schedule_background_collection("https://example.com")

        assert first_result is True
        assert second_result is False

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_allow_different_urls(self, mock_collect: AsyncMock) -> None:
        """Allow concurrent tasks for different URLs."""
        mock_collect.side_effect = lambda url: asyncio.sleep(5)

        result1 = await schedule_background_collection("https://example.com")
        result2 = await schedule_background_collection("https://other.com")

        assert result1 is True
        assert result2 is True

        count = await get_active_task_count()
        assert count == 2


class TestTaskMonitoring:
    """Tests for task monitoring utilities."""

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_active_task_count(self, mock_collect: AsyncMock) -> None:
        """Track active task count correctly."""
        mock_collect.side_effect = lambda url: asyncio.sleep(5)

        assert await get_active_task_count() == 0

        await schedule_background_collection("https://example.com")

        assert await get_active_task_count() == 1

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_is_url_being_collected(self, mock_collect: AsyncMock) -> None:
        """Check if a specific URL is being collected."""
        mock_collect.side_effect = lambda url: asyncio.sleep(5)

        assert await is_url_being_collected("https://example.com") is False

        await schedule_background_collection("https://example.com")

        assert await is_url_being_collected("https://example.com") is True
        assert await is_url_being_collected("https://other.com") is False


class TestTaskCleanup:
    """Tests for task cleanup and cancellation."""

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_cancel_all_tasks(self, mock_collect: AsyncMock) -> None:
        """Cancel all active background tasks."""
        mock_collect.side_effect = lambda url: asyncio.sleep(5)

        await schedule_background_collection("https://example1.com")
        await schedule_background_collection("https://example2.com")

        cancelled = await cancel_all_tasks()

        assert cancelled == 2
        assert await get_active_task_count() == 0

    @pytest.mark.asyncio
    @patch(
        "app.workers.collector.collect_metadata_background",
        new_callable=AsyncMock,
    )
    async def test_completed_tasks_cleaned_up(self, mock_collect: AsyncMock) -> None:
        """Completed tasks are removed from the registry."""
        # Task completes immediately
        mock_collect.return_value = None

        await schedule_background_collection("https://example.com")

        # Wait for task to complete
        await asyncio.sleep(0.2)

        count = await get_active_task_count()
        assert count == 0