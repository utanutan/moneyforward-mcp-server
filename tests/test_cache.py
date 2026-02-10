"""Tests for cache management functionality.

This module tests the CacheManager class including TTL-based caching
and snapshot functionality.
"""

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.cache.sqlite_cache import CacheManager


@pytest.fixture
async def cache_manager():
    """Create a temporary cache manager for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_cache.db")
        manager = CacheManager(db_path=db_path, default_ttl=5)
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.mark.asyncio
async def test_cache_set_and_get(cache_manager):
    """Test basic cache set and get operations."""
    test_data = {"key1": "value1", "key2": 123}

    # Set cache
    await cache_manager.set("test_key", test_data)

    # Get cache
    result = await cache_manager.get("test_key")

    assert result == test_data


@pytest.mark.asyncio
async def test_cache_miss(cache_manager):
    """Test cache miss returns None."""
    result = await cache_manager.get("nonexistent_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_ttl_expiration(cache_manager):
    """Test that cache expires after TTL."""
    test_data = {"test": "data"}

    # Set cache with 1 second TTL
    await cache_manager.set("ttl_test", test_data, ttl=1)

    # Should be available immediately
    result = await cache_manager.get("ttl_test")
    assert result == test_data

    # Wait for expiration
    await asyncio.sleep(1.5)

    # Should be None after expiration
    result = await cache_manager.get("ttl_test")
    assert result is None


@pytest.mark.asyncio
async def test_cache_update(cache_manager):
    """Test updating existing cache entry."""
    # Set initial data
    await cache_manager.set("update_test", {"version": 1})

    # Update data
    await cache_manager.set("update_test", {"version": 2})

    # Should get updated data
    result = await cache_manager.get("update_test")
    assert result == {"version": 2}


@pytest.mark.asyncio
async def test_cache_delete(cache_manager):
    """Test cache deletion."""
    test_data = {"test": "data"}

    # Set cache
    await cache_manager.set("delete_test", test_data)

    # Verify it exists
    result = await cache_manager.get("delete_test")
    assert result == test_data

    # Delete cache
    await cache_manager.delete("delete_test")

    # Should be None after deletion
    result = await cache_manager.get("delete_test")
    assert result is None


@pytest.mark.asyncio
async def test_cleanup_expired(cache_manager):
    """Test cleanup of expired cache entries."""
    # Set multiple entries with different TTLs
    await cache_manager.set("short_ttl", {"data": 1}, ttl=1)
    await cache_manager.set("long_ttl", {"data": 2}, ttl=10)

    # Wait for short TTL to expire
    await asyncio.sleep(1.5)

    # Cleanup expired entries
    deleted_count = await cache_manager.cleanup_expired()

    # Should have deleted at least 1 entry
    assert deleted_count >= 1

    # Short TTL entry should be gone
    result = await cache_manager.get("short_ttl")
    assert result is None

    # Long TTL entry should still exist
    result = await cache_manager.get("long_ttl")
    assert result == {"data": 2}


@pytest.mark.asyncio
async def test_save_snapshot(cache_manager):
    """Test saving asset snapshots."""
    snapshot_data = {
        "total_assets_jpy": 5000000,
        "daily_change_jpy": 12000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save snapshot
    await cache_manager.save_snapshot(snapshot_data)

    # Retrieve snapshots
    snapshots = await cache_manager.get_snapshots(days=1)

    # Should have at least one snapshot
    assert len(snapshots) >= 1

    # Check snapshot data (excluding the added timestamp field)
    latest = snapshots[0]
    assert latest["total_assets_jpy"] == snapshot_data["total_assets_jpy"]
    assert latest["daily_change_jpy"] == snapshot_data["daily_change_jpy"]
    assert "snapshot_created_at" in latest


@pytest.mark.asyncio
async def test_get_snapshots_with_days_filter(cache_manager):
    """Test filtering snapshots by days."""
    # Save multiple snapshots
    for i in range(5):
        await cache_manager.save_snapshot({"value": i})

    # Get snapshots from last 30 days
    snapshots = await cache_manager.get_snapshots(days=30)

    # Should have all 5 snapshots
    assert len(snapshots) >= 5


@pytest.mark.asyncio
async def test_cache_with_complex_data(cache_manager):
    """Test caching complex nested data structures."""
    complex_data = {
        "transactions": [
            {"date": "2025-01-01", "amount": 1000, "category": "Food"},
            {"date": "2025-01-02", "amount": 2000, "category": "Transport"},
        ],
        "metadata": {
            "total": 3000,
            "count": 2,
        },
    }

    await cache_manager.set("complex_test", complex_data)
    result = await cache_manager.get("complex_test")

    assert result == complex_data
    assert len(result["transactions"]) == 2
    assert result["metadata"]["total"] == 3000
