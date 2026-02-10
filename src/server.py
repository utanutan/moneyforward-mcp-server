"""FastMCP server entry point for MoneyForward ME MCP Server.

This module provides the main MCP server that exposes MoneyForward ME
data through FastMCP tools with caching and browser automation.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import yaml
from fastmcp import FastMCP

from src.browser.auth import AuthManager
from src.browser.context import BrowserManager
from src.browser.scraper import MoneyForwardScraper
from src.cache.sqlite_cache import CacheManager
from src.config import settings


# Configure structlog
def configure_logging() -> None:
    """Configure structlog for JSON or console output."""
    if settings.log_format == "json":
        processors = [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


# Initialize logging
configure_logging()
logger = structlog.get_logger(__name__)

# Global instances (initialized in lifespan)
browser_manager: BrowserManager | None = None
auth_manager: AuthManager | None = None
scraper: MoneyForwardScraper | None = None
cache_manager: CacheManager | None = None
selectors: dict | None = None


@asynccontextmanager
async def lifespan(server):
    """Manage server startup and shutdown."""
    global browser_manager, auth_manager, scraper, cache_manager, selectors

    logger.info(
        "mcp_server_starting",
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    # Load selectors
    try:
        selectors_path = Path(settings.selectors_path)
        with open(selectors_path, encoding="utf-8") as f:
            selectors = yaml.safe_load(f)
        logger.info("selectors_loaded", path=str(selectors_path))
    except Exception as e:
        logger.error("failed_to_load_selectors", error=str(e), exc_info=True)
        sys.exit(1)

    # Initialize browser manager
    try:
        browser_manager = BrowserManager.get_instance()
        await browser_manager.initialize()
        logger.info("browser_manager_initialized")
    except Exception as e:
        logger.error("browser_initialization_failed", error=str(e), exc_info=True)
        sys.exit(1)

    # Initialize auth manager
    try:
        auth_manager = AuthManager(browser_manager, selectors)
        logger.info("auth_manager_initialized")
    except Exception as e:
        logger.error("auth_manager_initialization_failed", error=str(e), exc_info=True)
        sys.exit(1)

    # Initialize scraper
    try:
        scraper = MoneyForwardScraper(browser_manager, auth_manager, selectors)
        logger.info("scraper_initialized")
    except Exception as e:
        logger.error("scraper_initialization_failed", error=str(e), exc_info=True)
        sys.exit(1)

    # Initialize cache manager
    try:
        cache_manager = CacheManager(
            db_path=settings.cache_db_path,
            default_ttl=settings.cache_ttl_seconds,
        )
        await cache_manager.initialize()
        logger.info("cache_manager_initialized")
    except Exception as e:
        logger.error("cache_initialization_failed", error=str(e), exc_info=True)
        sys.exit(1)

    logger.info("mcp_server_startup_complete")

    try:
        yield
    finally:
        logger.info("mcp_server_shutting_down")

        if cache_manager:
            try:
                await cache_manager.close()
                logger.info("cache_manager_closed")
            except Exception as e:
                logger.warning("cache_close_error", error=str(e))

        if browser_manager:
            try:
                await browser_manager.shutdown()
                logger.info("browser_manager_shutdown")
            except Exception as e:
                logger.warning("browser_shutdown_error", error=str(e))

        logger.info("mcp_server_shutdown_complete")


# Create FastMCP instance
mcp = FastMCP("MoneyForward MCP Server", lifespan=lifespan)


# Tool: Get Total Assets
@mcp.tool()
async def get_total_assets() -> dict:
    """Get current total assets and daily change from MoneyForward ME.

    Retrieves the total assets amount and daily change with caching support.
    Cache TTL is 5 minutes by default.

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Asset information (if success)
                - total_assets_jpy: Total assets in JPY (int)
                - daily_change_jpy: Daily change in JPY (int)
                - fetched_at: ISO 8601 timestamp
            - metadata: Response metadata
                - source: "scraping" or "cache"
                - cached: Whether data came from cache (bool)
                - cache_ttl_seconds: Cache TTL in seconds
    """
    from src.tools.assets import get_total_assets as get_assets_impl

    if not scraper or not cache_manager:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await get_assets_impl(scraper, cache_manager)


# Tool: List Recent Transactions
@mcp.tool()
async def list_recent_transactions(count: int = 20) -> dict:
    """List recent transactions from MoneyForward ME.

    Retrieves recent transactions with optional limit. Results are cached.

    Args:
        count: Maximum number of transactions to retrieve (1-100, default: 20)

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Transaction information (if success)
                - transactions: List of transaction dictionaries
                    - date: Transaction date (str)
                    - description: Transaction description (str)
                    - amount: Amount in JPY (int)
                    - category: Transaction category (str)
            - metadata: Response metadata
    """
    from src.tools.transactions import list_recent_transactions as list_txns_impl

    if not scraper or not cache_manager:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await list_txns_impl(scraper, cache_manager, count=count)


# Tool: Get Budget Status
@mcp.tool()
async def get_budget_status() -> dict:
    """Get current month's budget status from MoneyForward ME.

    Retrieves budget information including total, spent, and remaining amounts
    with category breakdowns.

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Budget information (if success)
                - month: Current month (YYYY-MM)
                - budget: Total budget in JPY (int)
                - spent: Total spent in JPY (int)
                - remaining: Remaining budget in JPY (int)
                - categories: List of category breakdowns
            - metadata: Response metadata
    """
    from src.tools.budget import get_budget_status as get_budget_impl

    if not scraper or not cache_manager:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await get_budget_impl(scraper, cache_manager)


# Tool: Trigger Account Refresh
@mcp.tool()
async def trigger_refresh() -> dict:
    """Trigger account refresh on MoneyForward ME.

    Initiates a refresh of all linked accounts. This is a real-time operation
    and does not use caching.

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Refresh result (if success)
                - status: Refresh status (str)
                - refreshed_at: ISO 8601 timestamp
            - metadata: Response metadata
    """
    from src.tools.refresh import trigger_refresh as trigger_refresh_impl

    if not scraper:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await trigger_refresh_impl(scraper)


# Tool: Health Check
@mcp.tool()
async def health_check() -> dict:
    """Check health of MCP server components.

    Verifies the status of browser, authentication session, and cache database.

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Health status (if success)
                - browser_status: Browser health (str)
                - session_valid: Whether session is valid (bool)
                - cache_status: Cache database status (str)
                - checked_at: ISO 8601 timestamp
            - metadata: Response metadata
    """
    from src.tools.health import health_check as health_check_impl

    if not scraper or not cache_manager:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await health_check_impl(scraper, cache_manager)


# Tool: List Manual Accounts
@mcp.tool()
async def list_manual_accounts() -> dict:
    """List manual accounts configured for foreign currency management.

    Reads account configurations from accounts.yaml. These are manually
    managed accounts (e.g., overseas bank accounts, securities) that are
    tracked in MoneyForward ME with JPY-converted balances.

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Account information (if success)
                - accounts: List of account dictionaries
                    - name: Account name (str)
                    - type: Account type - "bank" or "securities" (str)
                    - currency: Foreign currency code (str)
                    - mf_display_name: Display name on MoneyForward ME (str)
                - count: Number of accounts (int)
            - metadata: Response metadata
    """
    from src.tools.manual_accounts import list_manual_accounts as list_accounts_impl

    return await list_accounts_impl()


# Tool: Update Manual Account
@mcp.tool()
async def update_manual_account(account_name: str, amount_myr: float) -> dict:
    """Update a manual account balance with MYR to JPY conversion.

    Converts the specified MYR amount to JPY using a live exchange rate,
    then updates the corresponding manual account on MoneyForward ME.

    Args:
        account_name: Account name as defined in accounts.yaml (e.g., "Wise", "CIMB")
        amount_myr: Current balance in MYR (Malaysian Ringgit)

    Returns:
        Dictionary containing:
            - status: "success" or "error"
            - data: Update result (if success)
                - account_name: Account name (str)
                - mf_display_name: MoneyForward ME display name (str)
                - amount_myr: Original MYR amount (float)
                - amount_jpy: Converted JPY amount (int)
                - exchange_rate: MYR to JPY rate used (float)
                - currency: Currency code (str)
                - updated_at: ISO 8601 timestamp (str)
            - metadata: Response metadata
    """
    from src.tools.manual_accounts import update_manual_account as update_account_impl

    if not scraper:
        logger.error("server_not_initialized")
        return {
            "status": "error",
            "error": {"message": "Server not initialized", "type": "INITIALIZATION_ERROR"},
        }

    return await update_account_impl(scraper, account_name, amount_myr)


# HTTP health endpoint (for Docker healthcheck)
@mcp.custom_route("/health", methods=["GET"])
async def http_health(request) -> dict:
    """HTTP endpoint for Docker healthcheck.

    Returns:
        Simple health status for container orchestration.
    """
    try:
        if not browser_manager or not cache_manager or not scraper:
            return {"status": "initializing"}

        # Quick health check
        session_valid = False
        if auth_manager:
            try:
                session_valid = await auth_manager.is_session_valid()
            except Exception:
                pass

        return {
            "status": "healthy",
            "session_valid": session_valid,
        }
    except Exception as e:
        logger.error("http_health_check_failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    # This allows running the server directly with `python src/server.py`
    # but the recommended way is: uv run fastmcp run src/server.py
    logger.info("starting_mcp_server_directly")
    mcp.run()
