"""Tests for MCP tools functionality.

This module tests the MCP tools including response formatting,
caching behavior, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tools.assets import get_total_assets
from src.tools.budget import get_budget_status
from src.tools.common import build_error_response, build_success_response, cached_tool_call
from src.tools.health import health_check
from src.tools.refresh import trigger_refresh
from src.tools.transactions import list_recent_transactions


def test_build_success_response():
    """Test building success response."""
    data = {"total_assets_jpy": 5000000, "daily_change_jpy": 12000}

    response = build_success_response(data, source="scraping", cached=False)

    assert response["status"] == "success"
    assert response["data"] == data
    assert response["metadata"]["source"] == "scraping"
    assert response["metadata"]["cached"] is False
    assert "fetched_at" in response["metadata"]
    assert "cache_ttl_seconds" in response["metadata"]


def test_build_error_response():
    """Test building error response."""
    message = "Test error message"
    error_type = "TEST_ERROR"

    response = build_error_response(message, error_type)

    assert response["status"] == "error"
    assert response["error"]["message"] == message
    assert response["error"]["type"] == error_type
    assert "fetched_at" in response["metadata"]


@pytest.mark.asyncio
async def test_cached_tool_call_cache_hit():
    """Test cached tool call with cache hit."""
    # Mock cache manager with cached data
    cache_manager = AsyncMock()
    cached_data = {"total_assets_jpy": 5000000}
    cache_manager.get.return_value = cached_data

    # Mock scrape function (should not be called)
    scrape_fn = AsyncMock()

    # Execute cached tool call
    response = await cached_tool_call(
        cache_manager=cache_manager,
        cache_key="test_key",
        scrape_fn=scrape_fn,
    )

    # Verify cache was checked
    cache_manager.get.assert_called_once_with("test_key")

    # Verify scrape function was NOT called
    scrape_fn.assert_not_called()

    # Verify response
    assert response["status"] == "success"
    assert response["data"] == cached_data
    assert response["metadata"]["cached"] is True
    assert response["metadata"]["source"] == "cache"


@pytest.mark.asyncio
async def test_cached_tool_call_cache_miss():
    """Test cached tool call with cache miss."""
    # Mock cache manager with no cached data
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Mock scrape function
    scraped_data = {"total_assets_jpy": 6000000}
    scrape_fn = AsyncMock(return_value=scraped_data)

    # Execute cached tool call
    response = await cached_tool_call(
        cache_manager=cache_manager,
        cache_key="test_key",
        scrape_fn=scrape_fn,
    )

    # Verify cache was checked
    cache_manager.get.assert_called_once_with("test_key")

    # Verify scrape function was called
    scrape_fn.assert_called_once()

    # Verify cache was updated
    cache_manager.set.assert_called_once_with("test_key", scraped_data)

    # Verify response
    assert response["status"] == "success"
    assert response["data"] == scraped_data
    assert response["metadata"]["cached"] is False
    assert response["metadata"]["source"] == "scraping"


@pytest.mark.asyncio
async def test_get_total_assets_success():
    """Test get_total_assets tool with successful scraping."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.get_total_assets.return_value = {
        "total_assets_jpy": 5000000,
        "daily_change_jpy": 12000,
        "fetched_at": "2025-01-01T00:00:00+09:00",
    }

    # Mock cache manager (cache miss)
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Call tool
    response = await get_total_assets(scraper, cache_manager)

    # Verify response
    assert response["status"] == "success"
    assert "total_assets_jpy" in response["data"]
    assert "daily_change_jpy" in response["data"]


@pytest.mark.asyncio
async def test_list_recent_transactions_success():
    """Test list_recent_transactions tool."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.get_recent_transactions.return_value = [
        {"date": "2025-01-01", "amount": 1000, "description": "Test", "category": "Food"}
    ]

    # Mock cache manager (cache miss)
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Call tool
    response = await list_recent_transactions(scraper, cache_manager, count=10)

    # Verify response
    assert response["status"] == "success"
    assert "transactions" in response["data"]
    assert len(response["data"]["transactions"]) == 1


@pytest.mark.asyncio
async def test_list_recent_transactions_count_validation():
    """Test count parameter validation."""
    scraper = AsyncMock()
    scraper.get_recent_transactions.return_value = []

    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Test with count < 1 (should be clamped to 1)
    await list_recent_transactions(scraper, cache_manager, count=0)
    scraper.get_recent_transactions.assert_called_with(limit=1)

    # Test with count > 100 (should be clamped to 100)
    await list_recent_transactions(scraper, cache_manager, count=150)
    scraper.get_recent_transactions.assert_called_with(limit=100)


@pytest.mark.asyncio
async def test_get_budget_status_success():
    """Test get_budget_status tool."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.get_budget_status.return_value = {
        "month": "2025-01",
        "budget": 300000,
        "spent": 150000,
        "remaining": 150000,
        "categories": [],
    }

    # Mock cache manager (cache miss)
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Call tool
    response = await get_budget_status(scraper, cache_manager)

    # Verify response
    assert response["status"] == "success"
    assert response["data"]["budget"] == 300000
    assert response["data"]["remaining"] == 150000


@pytest.mark.asyncio
async def test_trigger_refresh_success():
    """Test trigger_refresh tool."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.trigger_account_refresh.return_value = {
        "status": "refresh_triggered",
        "refreshed_at": "2025-01-01T00:00:00+09:00",
    }

    # Call tool (no cache manager needed)
    response = await trigger_refresh(scraper)

    # Verify response
    assert response["status"] == "success"
    assert response["data"]["status"] == "refresh_triggered"
    assert response["metadata"]["cached"] is False


@pytest.mark.asyncio
async def test_health_check_success():
    """Test health_check tool."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.check_health.return_value = {
        "browser_status": "ok",
        "session_valid": True,
        "checked_at": "2025-01-01T00:00:00+09:00",
    }

    # Mock cache manager
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Call tool
    response = await health_check(scraper, cache_manager)

    # Verify response
    assert response["status"] == "success"
    assert response["data"]["browser_status"] == "ok"
    assert response["data"]["session_valid"] is True
    assert "cache_status" in response["data"]


@pytest.mark.asyncio
async def test_health_check_cache_error():
    """Test health_check with cache error."""
    # Mock scraper
    scraper = AsyncMock()
    scraper.check_health.return_value = {
        "browser_status": "ok",
        "session_valid": True,
        "checked_at": "2025-01-01T00:00:00+09:00",
    }

    # Mock cache manager with error
    cache_manager = AsyncMock()
    cache_manager.get.side_effect = Exception("Cache connection failed")

    # Call tool
    response = await health_check(scraper, cache_manager)

    # Verify response
    assert response["status"] == "success"
    assert "error" in response["data"]["cache_status"]


@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test error handling in tools."""
    # Mock scraper that raises an error
    scraper = AsyncMock()
    scraper.get_total_assets.side_effect = Exception("Scraping failed")

    # Mock cache manager (cache miss)
    cache_manager = AsyncMock()
    cache_manager.get.return_value = None

    # Call tool
    response = await get_total_assets(scraper, cache_manager)

    # Verify error response
    assert response["status"] == "error"
    assert "SCRAPING_ERROR" in response["error"]["type"]
    assert "Failed to get total assets" in response["error"]["message"]
