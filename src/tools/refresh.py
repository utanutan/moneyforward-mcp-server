"""MCP tool for triggering account refresh.

This module provides the trigger_refresh tool which initiates a
refresh of linked accounts on MoneyForward ME.
"""

from typing import Any

import structlog

from src.tools.common import build_error_response, build_success_response

logger = structlog.get_logger(__name__)


async def trigger_refresh(
    scraper: Any,
) -> dict[str, Any]:
    """Trigger account refresh on MoneyForward ME.

    Initiates a refresh of all linked accounts. This operation does not use
    caching as it performs a real-time action.

    Args:
        scraper: MoneyForwardScraper instance.

    Returns:
        Standardized response containing:
            - status: Refresh status
            - refreshed_at: Timestamp of refresh trigger

    Examples:
        >>> response = await trigger_refresh(scraper)
        >>> print(response["data"]["status"])
        'refresh_triggered'
    """
    logger.info("trigger_refresh_called")

    try:
        result = await scraper.trigger_account_refresh()
        return build_success_response(result, source="scraping", cached=False)

    except Exception as e:
        logger.error("trigger_refresh_failed", error=str(e), exc_info=True)
        return build_error_response(
            message=f"Failed to trigger refresh: {str(e)}",
            error_type="SCRAPING_ERROR",
        )
