"""MCP tool for health checking.

This module provides the health_check tool which verifies the status of
the browser, authentication session, and cache database.
"""

from typing import Any

import structlog

from src.tools.common import build_error_response, build_success_response

logger = structlog.get_logger(__name__)


async def health_check(
    scraper: Any,
    cache_manager: Any,
) -> dict[str, Any]:
    """Check health of MCP server components.

    Verifies the status of:
    - Browser instance
    - MoneyForward ME session
    - Cache database connection

    Args:
        scraper: MoneyForwardScraper instance.
        cache_manager: CacheManager instance.

    Returns:
        Standardized response containing:
            - browser_status: Browser health status
            - session_valid: Whether the session is valid
            - cache_status: Cache database status
            - checked_at: Timestamp of health check

    Examples:
        >>> response = await health_check(scraper, cache)
        >>> print(response["data"]["session_valid"])
        True
    """
    logger.info("health_check_called")

    try:
        # Check scraper/browser health
        scraper_health = await scraper.check_health()

        # Check cache database
        cache_status = "ok"
        try:
            # Try a simple cache operation to verify connection
            await cache_manager.get("_health_check")
            cache_status = "ok"
        except Exception as e:
            logger.warning("cache_health_check_failed", error=str(e))
            cache_status = f"error: {str(e)}"

        result = {
            "browser_status": scraper_health.get("browser_status", "unknown"),
            "session_valid": scraper_health.get("session_valid", False),
            "cache_status": cache_status,
            "checked_at": scraper_health.get("checked_at", ""),
        }

        return build_success_response(result, source="health_check", cached=False)

    except Exception as e:
        logger.error("health_check_failed", error=str(e), exc_info=True)
        return build_error_response(
            message=f"Health check failed: {str(e)}",
            error_type="HEALTH_CHECK_ERROR",
        )
