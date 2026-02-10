"""SQLite-based cache manager with TTL support and snapshot functionality.

This module provides a CacheManager class that handles:
- TTL-based key-value caching with JSON serialization
- Daily asset snapshots for historical tracking
- Automatic cleanup of expired cache entries
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

logger = structlog.get_logger(__name__)


class CacheManager:
    """SQLite-based cache manager with TTL and snapshot support.

    This class manages a SQLite database for caching scraped data and
    storing daily asset snapshots for historical analysis.

    Attributes:
        db_path: Path to the SQLite database file.
        default_ttl: Default TTL in seconds for cached entries.
    """

    def __init__(self, db_path: str, default_ttl: int = 300) -> None:
        """Initialize CacheManager.

        Args:
            db_path: Path to SQLite database file.
            default_ttl: Default TTL in seconds (default: 5 minutes).
        """
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._db: aiosqlite.Connection | None = None

        logger.info(
            "cache_manager_initialized",
            db_path=db_path,
            default_ttl=default_ttl,
        )

    async def initialize(self) -> None:
        """Initialize database connection and create tables.

        Creates the following tables if they don't exist:
        - cache: TTL-based key-value cache
        - snapshots: Daily asset snapshots
        """
        async with self._lock:
            # Ensure directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Connect to database
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row

            # Create cache table
            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

            # Create snapshots table
            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )

            # Create indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at)"
            )

            await self._db.commit()

            logger.info("cache_database_initialized", db_path=self.db_path)

    async def get(self, key: str) -> Any | None:
        """Get cached value by key.

        Returns None if key doesn't exist or TTL has expired.

        Args:
            key: Cache key.

        Returns:
            Cached value (deserialized from JSON) or None.
        """
        if not self._db:
            await self.initialize()

        async with self._lock:
            cursor = await self._db.execute(  # type: ignore
                "SELECT data, expires_at FROM cache WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()

            if not row:
                logger.debug("cache_miss", key=key)
                return None

            # Check TTL
            expires_at = datetime.fromisoformat(row["expires_at"])
            now = datetime.now(timezone.utc)

            if now > expires_at:
                logger.debug("cache_expired", key=key)
                # Clean up expired entry
                await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))  # type: ignore
                await self._db.commit()  # type: ignore
                return None

            # Return cached data
            data = json.loads(row["data"])
            logger.debug("cache_hit", key=key)
            return data

    async def set(self, key: str, data: Any, ttl: int | None = None) -> None:
        """Set cached value with TTL.

        Args:
            key: Cache key.
            data: Data to cache (will be JSON serialized).
            ttl: Time to live in seconds. If None, uses default_ttl.
        """
        if not self._db:
            await self.initialize()

        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

        async with self._lock:
            await self._db.execute(  # type: ignore
                """
                INSERT OR REPLACE INTO cache (key, data, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(data), expires_at.isoformat()),
            )
            await self._db.commit()  # type: ignore

            logger.debug(
                "cache_set",
                key=key,
                ttl_seconds=ttl_seconds,
                expires_at=expires_at.isoformat(),
            )

    async def delete(self, key: str) -> None:
        """Delete a cache entry.

        Args:
            key: Cache key to delete.
        """
        if not self._db:
            await self.initialize()

        async with self._lock:
            await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))  # type: ignore
            await self._db.commit()  # type: ignore

            logger.debug("cache_deleted", key=key)

    async def cleanup_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries deleted.
        """
        if not self._db:
            await self.initialize()

        now = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            cursor = await self._db.execute(  # type: ignore
                "DELETE FROM cache WHERE expires_at < ? RETURNING key",
                (now,),
            )
            deleted_rows = await cursor.fetchall()
            count = len(deleted_rows)
            await self._db.commit()  # type: ignore

            logger.info("cache_cleanup_completed", deleted_count=count)
            return count

    async def save_snapshot(self, data: dict[str, Any]) -> None:
        """Save a daily asset snapshot.

        Args:
            data: Snapshot data to save (will be JSON serialized).
        """
        if not self._db:
            await self.initialize()

        async with self._lock:
            await self._db.execute(  # type: ignore
                "INSERT INTO snapshots (data) VALUES (?)",
                (json.dumps(data),),
            )
            await self._db.commit()  # type: ignore

            logger.info("snapshot_saved", data_keys=list(data.keys()))

    async def get_snapshots(self, days: int = 30) -> list[dict[str, Any]]:
        """Get recent snapshots.

        Args:
            days: Number of days to retrieve (default: 30).

        Returns:
            List of snapshot dictionaries.
        """
        if not self._db:
            await self.initialize()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        async with self._lock:
            cursor = await self._db.execute(  # type: ignore
                """
                SELECT data, created_at
                FROM snapshots
                WHERE created_at >= ?
                ORDER BY created_at DESC
                """,
                (cutoff.isoformat(),),
            )
            rows = await cursor.fetchall()

            snapshots = []
            for row in rows:
                snapshot = json.loads(row["data"])
                snapshot["snapshot_created_at"] = row["created_at"]
                snapshots.append(snapshot)

            logger.debug("snapshots_retrieved", count=len(snapshots), days=days)
            return snapshots

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("cache_database_closed")
