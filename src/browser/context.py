"""Browser context management with Playwright persistent context.

This module provides a singleton BrowserManager that manages a single Playwright
Chromium instance with persistent context for session management across multiple
tool invocations.
"""

import asyncio
from typing import ClassVar

import structlog
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.config import settings

logger = structlog.get_logger(__name__)


class BrowserManager:
    """Singleton manager for Playwright browser instance with persistent context.

    This class maintains a single Chromium browser instance throughout the application
    lifecycle, using persistent context to preserve login sessions and cookies.

    Usage:
        manager = BrowserManager.get_instance()
        await manager.initialize()
        page = await manager.new_page()
        # ... use page ...
        await page.close()
        # On shutdown:
        await manager.shutdown()
    """

    _instance: ClassVar["BrowserManager | None"] = None
    _playwright: Playwright | None
    _context: BrowserContext | None
    _lock: asyncio.Lock

    def __init__(self) -> None:
        """Initialize browser manager (use get_instance() instead)."""
        self._playwright = None
        self._context = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        """Get the singleton instance of BrowserManager.

        Returns:
            The singleton BrowserManager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        """Initialize Playwright and launch persistent browser context.

        This should be called once during application startup. It launches a
        Chromium browser with persistent context to preserve sessions.

        Raises:
            RuntimeError: If browser fails to launch.
        """
        async with self._lock:
            if self._context is not None:
                logger.info("browser_already_initialized")
                return

            try:
                logger.info("initializing_playwright")
                self._playwright = await async_playwright().start()

                logger.info(
                    "launching_persistent_context",
                    user_data_dir=settings.browser_context_dir,
                    headless=settings.browser_headless,
                )

                # Launch persistent context with session preservation
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=settings.browser_context_dir,
                    headless=settings.browser_headless,
                    locale="ja-JP",
                    timezone_id="Asia/Tokyo",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )

                logger.info(
                    "browser_initialized_successfully",
                    context_pages=len(self._context.pages),
                )

            except Exception as e:
                logger.error(
                    "browser_initialization_failed",
                    error=str(e),
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to initialize browser: {e}") from e

    async def get_context(self) -> BrowserContext:
        """Get the current browser context.

        If not initialized, this will call initialize() first.

        Returns:
            The persistent browser context.

        Raises:
            RuntimeError: If context initialization fails.
        """
        if self._context is None:
            await self.initialize()

        if self._context is None:
            raise RuntimeError("Browser context is not available")

        return self._context

    async def new_page(self) -> Page:
        """Create a new page in the browser context.

        The caller is responsible for closing the page after use.

        Returns:
            A new browser page.

        Raises:
            RuntimeError: If context is not available.
        """
        context = await self.get_context()
        page = await context.new_page()

        logger.debug(
            "new_page_created",
            total_pages=len(context.pages),
        )

        return page

    async def shutdown(self) -> None:
        """Shutdown the browser and Playwright.

        This should be called during application shutdown to properly close
        the browser and release resources.
        """
        async with self._lock:
            if self._context is not None:
                logger.info("closing_browser_context")
                try:
                    await self._context.close()
                except Exception as e:
                    logger.warning(
                        "error_closing_context",
                        error=str(e),
                    )
                finally:
                    self._context = None

            if self._playwright is not None:
                logger.info("stopping_playwright")
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(
                        "error_stopping_playwright",
                        error=str(e),
                    )
                finally:
                    self._playwright = None

            logger.info("browser_shutdown_complete")
