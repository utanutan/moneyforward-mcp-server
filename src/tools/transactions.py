"""MCP tool for retrieving recent transactions.

This module provides the list_recent_transactions tool which retrieves
recent transactions from MoneyForward ME with caching support.
"""

from typing import Any

import structlog

from src.tools.common import build_error_response, cached_tool_call

logger = structlog.get_logger(__name__)


async def list_recent_transactions(
    scraper: Any,
    cache_manager: Any,
    count: int = 20,
) -> dict[str, Any]:
    """List recent transactions from MoneyForward ME.

    Retrieves the most recent transactions with optional limit.
    Results are cached with TTL to reduce scraping frequency.

    Args:
        scraper: MoneyForwardScraper instance.
        cache_manager: CacheManager instance.
        count: Maximum number of transactions to retrieve (default: 20, max: 100).

    Returns:
        Standardized response containing a list of transactions.
        Each transaction includes:
            - date: Transaction date
            - description: Transaction description
            - amount: Amount in JPY
            - category: Transaction category

    Examples:
        >>> response = await list_recent_transactions(scraper, cache, count=10)
        >>> print(len(response["data"]["transactions"]))
        10
    """
    logger.info("list_recent_transactions_called", count=count)

    # Validate count parameter
    if count < 1:
        count = 1
    elif count > 100:
        count = 100

    try:
        cache_key = f"transactions_{count}"

        async def scrape_transactions() -> dict[str, Any]:
            transactions = await scraper.get_recent_transactions(limit=count)
            return {"transactions": transactions}

        return await cached_tool_call(
            cache_manager=cache_manager,
            cache_key=cache_key,
            scrape_fn=scrape_transactions,
        )

    except Exception as e:
        logger.error(
            "list_recent_transactions_failed",
            count=count,
            error=str(e),
            exc_info=True,
        )
        return build_error_response(
            message=f"Failed to list transactions: {str(e)}",
            error_type="SCRAPING_ERROR",
        )
