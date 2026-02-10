"""Common utilities for MCP tools.

This module provides shared functionality for all MCP tools including:
- Unified response formatting
- Error handling
- Caching patterns
"""

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)


def build_success_response(
    data: dict[str, Any],
    source: str = "scraping",
    cached: bool = False,
) -> dict[str, Any]:
    """Build a standardized success response.

    Args:
        data: The response data.
        source: Data source ("scraping" or "cache").
        cached: Whether the data came from cache.

    Returns:
        Standardized response dictionary.
    """
    jst = timezone(timedelta(hours=9))
    return {
        "status": "success",
        "data": data,
        "metadata": {
            "fetched_at": datetime.now(jst).isoformat(),
            "source": source,
            "cached": cached,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
        },
    }


def build_error_response(
    message: str,
    error_type: str = "UNKNOWN_ERROR",
) -> dict[str, Any]:
    """Build a standardized error response.

    Args:
        message: Error message.
        error_type: Error type identifier.

    Returns:
        Standardized error response dictionary.
    """
    jst = timezone(timedelta(hours=9))
    return {
        "status": "error",
        "error": {
            "message": message,
            "type": error_type,
        },
        "metadata": {
            "fetched_at": datetime.now(jst).isoformat(),
        },
    }


async def cached_tool_call(
    cache_manager: Any,
    cache_key: str,
    scrape_fn: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a tool with caching support.

    This pattern checks cache first, then falls back to scraping if needed.

    Args:
        cache_manager: CacheManager instance.
        cache_key: Key for caching the result.
        scrape_fn: Async function to call if cache miss.
        *args: Positional arguments for scrape_fn.
        **kwargs: Keyword arguments for scrape_fn.

    Returns:
        Standardized response dictionary.
    """
    # Try cache first
    cached_data = await cache_manager.get(cache_key)
    if cached_data:
        logger.debug("cache_hit", cache_key=cache_key)
        return build_success_response(cached_data, source="cache", cached=True)

    # Cache miss - scrape data
    logger.debug("cache_miss", cache_key=cache_key)

    try:
        data = await scrape_fn(*args, **kwargs)

        # Save to cache
        await cache_manager.set(cache_key, data)

        return build_success_response(data, source="scraping", cached=False)

    except Exception as e:
        logger.error(
            "scraping_failed",
            cache_key=cache_key,
            error=str(e),
            exc_info=True,
        )
        raise
