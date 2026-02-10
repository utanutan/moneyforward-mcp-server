"""MCP tool for retrieving total assets.

This module provides the get_total_assets tool which retrieves the current
total assets and daily change from MoneyForward ME with caching support.
"""

from typing import Any

import structlog

from src.tools.common import build_error_response, cached_tool_call

logger = structlog.get_logger(__name__)


async def get_total_assets(
    scraper: Any,
    cache_manager: Any,
) -> dict[str, Any]:
    """Get current total assets and daily change.

    Retrieves the total assets amount and daily change from MoneyForward ME.
    Results are cached with TTL to reduce scraping frequency.

    Args:
        scraper: MoneyForwardScraper instance.
        cache_manager: CacheManager instance.

    Returns:
        Standardized response containing:
            - total_assets_jpy: Total assets in JPY
            - daily_change_jpy: Daily change in JPY
            - fetched_at: Timestamp of data retrieval

    Examples:
        >>> response = await get_total_assets(scraper, cache)
        >>> print(response["data"]["total_assets_jpy"])
        5000000
    """
    logger.info("get_total_assets_called")

    try:
        return await cached_tool_call(
            cache_manager=cache_manager,
            cache_key="total_assets",
            scrape_fn=scraper.get_total_assets,
        )
    except Exception as e:
        logger.error("get_total_assets_failed", error=str(e), exc_info=True)
        return build_error_response(
            message=f"Failed to get total assets: {str(e)}",
            error_type="SCRAPING_ERROR",
        )
