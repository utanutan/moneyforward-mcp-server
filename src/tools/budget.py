"""MCP tool for retrieving budget status.

This module provides the get_budget_status tool which retrieves the current
month's budget consumption status from MoneyForward ME with caching support.
"""

from typing import Any

import structlog

from src.tools.common import build_error_response, cached_tool_call

logger = structlog.get_logger(__name__)


async def get_budget_status(
    scraper: Any,
    cache_manager: Any,
) -> dict[str, Any]:
    """Get current month's budget status.

    Retrieves budget information including total budget, spent amount,
    remaining budget, and category breakdowns.
    Results are cached with TTL to reduce scraping frequency.

    Args:
        scraper: MoneyForwardScraper instance.
        cache_manager: CacheManager instance.

    Returns:
        Standardized response containing:
            - month: Current month (YYYY-MM)
            - budget: Total budget in JPY
            - spent: Total spent in JPY
            - remaining: Remaining budget in JPY
            - categories: List of category breakdowns

    Examples:
        >>> response = await get_budget_status(scraper, cache)
        >>> print(response["data"]["remaining"])
        150000
    """
    logger.info("get_budget_status_called")

    try:
        return await cached_tool_call(
            cache_manager=cache_manager,
            cache_key="budget_status",
            scrape_fn=scraper.get_budget_status,
        )
    except Exception as e:
        logger.error("get_budget_status_failed", error=str(e), exc_info=True)
        return build_error_response(
            message=f"Failed to get budget status: {str(e)}",
            error_type="SCRAPING_ERROR",
        )
