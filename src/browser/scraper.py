"""Web scraping functionality for MoneyForward ME.

This module provides the MoneyForwardScraper class that handles all data extraction
from MoneyForward ME pages, including total assets, transactions, budget status,
and account refresh operations.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from playwright.async_api import Page

from src.browser.auth import AuthManager
from src.browser.context import BrowserManager

logger = structlog.get_logger(__name__)


class ScraperError(Exception):
    """Raised when scraping operations fail."""

    pass


class MoneyForwardScraper:
    """Scraper for MoneyForward ME data extraction.

    This class provides methods to extract various financial data from
    MoneyForward ME pages including assets, transactions, budget, and
    account refresh status.

    Attributes:
        browser: BrowserManager instance for page access.
        auth: AuthManager instance for authentication.
        selectors: CSS selectors loaded from selectors.yaml.
    """

    def __init__(
        self,
        browser: BrowserManager,
        auth: AuthManager,
        selectors: dict[str, Any],
    ) -> None:
        """Initialize MoneyForwardScraper.

        Args:
            browser: BrowserManager instance.
            auth: AuthManager instance.
            selectors: Dictionary of CSS selectors from selectors.yaml.
        """
        self.browser = browser
        self.auth = auth
        self.selectors = selectors

    async def get_total_assets(self) -> dict[str, Any]:
        """Scrape total assets and daily change from portfolio page.

        Returns:
            Dictionary containing:
                - total_assets_jpy: Total assets in JPY (int)
                - daily_change_jpy: Daily change in JPY (int, can be negative)
                - fetched_at: ISO 8601 timestamp string

        Raises:
            ScraperError: If scraping fails.
        """
        logger.info("scraping_total_assets")

        # Ensure authenticated before scraping
        await self.auth.ensure_authenticated()

        page = await self.browser.new_page()
        try:
            # Navigate to portfolio page
            url = self.selectors["portfolio"]["url"]
            await self._navigate_and_wait(page, url)

            # Extract total assets
            total_assets_selector = self.selectors["portfolio"]["total_assets"]
            total_assets_text = await self._extract_text(page, total_assets_selector)

            if not total_assets_text:
                raise ScraperError("Failed to extract total assets")

            total_assets_jpy = self._parse_currency(total_assets_text)

            # Extract daily change
            daily_change_selector = self.selectors["portfolio"]["daily_change"]
            daily_change_text = await self._extract_text(page, daily_change_selector)

            daily_change_jpy = 0
            if daily_change_text:
                daily_change_jpy = self._parse_currency(daily_change_text)

            result = {
                "total_assets_jpy": total_assets_jpy,
                "daily_change_jpy": daily_change_jpy,
                "fetched_at": self._get_current_timestamp(),
            }

            logger.info(
                "total_assets_scraped_successfully",
                total_assets_jpy=total_assets_jpy,
                daily_change_jpy=daily_change_jpy,
            )

            return result

        except Exception as e:
            logger.error(
                "total_assets_scraping_failed",
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(f"Failed to scrape total assets: {e}") from e

        finally:
            await page.close()

    async def get_recent_transactions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Scrape recent transactions from cash flow page.

        Args:
            limit: Maximum number of transactions to retrieve (default: 20).

        Returns:
            List of transaction dictionaries, each containing:
                - date: Transaction date (str)
                - description: Transaction description (str)
                - amount: Transaction amount in JPY (int)
                - category: Transaction category (str)

        Raises:
            ScraperError: If scraping fails.
        """
        logger.info("scraping_recent_transactions", limit=limit)

        # Ensure authenticated before scraping
        await self.auth.ensure_authenticated()

        page = await self.browser.new_page()
        try:
            # Navigate to transactions page
            url = self.selectors["transactions"]["url"]
            await self._navigate_and_wait(page, url)

            # Extract transactions table
            table_selector = self.selectors["transactions"]["table"]
            row_selector = self.selectors["transactions"]["rows"]

            # Wait for table to load
            await page.wait_for_selector(table_selector, timeout=10000)

            # Get all transaction rows
            rows = await page.query_selector_all(row_selector)

            transactions = []
            for i, row in enumerate(rows[:limit]):
                try:
                    # Extract transaction data
                    date_text = await row.query_selector(
                        self.selectors["transactions"]["date"]
                    )
                    description_text = await row.query_selector(
                        self.selectors["transactions"]["description"]
                    )
                    amount_text = await row.query_selector(
                        self.selectors["transactions"]["amount"]
                    )
                    category_text = await row.query_selector(
                        self.selectors["transactions"]["category"]
                    )

                    transaction = {
                        "date": await date_text.inner_text() if date_text else "",
                        "description": (
                            await description_text.inner_text()
                            if description_text
                            else ""
                        ),
                        "amount": self._parse_currency(
                            await amount_text.inner_text() if amount_text else "0"
                        ),
                        "category": (
                            await category_text.inner_text() if category_text else ""
                        ),
                    }

                    transactions.append(transaction)

                except Exception as e:
                    logger.warning(
                        "transaction_row_parse_error",
                        row_index=i,
                        error=str(e),
                    )
                    continue

            logger.info(
                "transactions_scraped_successfully",
                count=len(transactions),
            )

            return transactions

        except Exception as e:
            logger.error(
                "transactions_scraping_failed",
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(f"Failed to scrape transactions: {e}") from e

        finally:
            await page.close()

    async def trigger_account_refresh(self) -> dict[str, Any]:
        """Trigger account refresh and wait for completion.

        Returns:
            Dictionary containing:
                - status: Refresh status (str)
                - refreshed_at: ISO 8601 timestamp string

        Raises:
            ScraperError: If refresh operation fails.
        """
        logger.info("triggering_account_refresh")

        # Ensure authenticated before operation
        await self.auth.ensure_authenticated()

        page = await self.browser.new_page()
        try:
            # Navigate to accounts page
            url = self.selectors["refresh"]["url"]
            await self._navigate_and_wait(page, url)

            # Click refresh button
            refresh_button = self.selectors["refresh"]["refresh_button"]
            await page.wait_for_selector(refresh_button, timeout=10000)
            await page.click(refresh_button)

            logger.debug("refresh_button_clicked")

            # Wait for refresh to start (brief delay)
            await page.wait_for_timeout(2000)

            # Check status indicator
            status_selector = self.selectors["refresh"]["status_indicator"]
            status_text = await self._extract_text(page, status_selector)

            result = {
                "status": status_text or "refresh_triggered",
                "refreshed_at": self._get_current_timestamp(),
            }

            logger.info("account_refresh_triggered", status=result["status"])

            return result

        except Exception as e:
            logger.error(
                "account_refresh_failed",
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(f"Failed to trigger account refresh: {e}") from e

        finally:
            await page.close()

    async def get_budget_status(self) -> dict[str, Any]:
        """Scrape budget status from spending page.

        Returns:
            Dictionary containing:
                - month: Current month (str)
                - budget: Total budget in JPY (int)
                - spent: Total spent in JPY (int)
                - remaining: Remaining budget in JPY (int)
                - categories: List of category breakdowns

        Raises:
            ScraperError: If scraping fails.
        """
        logger.info("scraping_budget_status")

        # Ensure authenticated before scraping
        await self.auth.ensure_authenticated()

        page = await self.browser.new_page()
        try:
            # Navigate to budget page
            url = self.selectors["budget"]["url"]
            await self._navigate_and_wait(page, url)

            # Extract total budget
            total_budget_text = await self._extract_text(
                page, self.selectors["budget"]["total_budget"]
            )
            total_budget = self._parse_currency(total_budget_text or "0")

            # Extract total spent
            total_spent_text = await self._extract_text(
                page, self.selectors["budget"]["total_spent"]
            )
            total_spent = self._parse_currency(total_spent_text or "0")

            # Calculate remaining
            remaining = total_budget - total_spent

            # Extract category breakdowns
            categories = []
            category_selector = self.selectors["budget"]["categories"]
            category_elements = await page.query_selector_all(category_selector)

            for elem in category_elements:
                try:
                    category_name = await elem.inner_text()
                    categories.append({"name": category_name})
                except Exception as e:
                    logger.warning("category_parse_error", error=str(e))
                    continue

            result = {
                "month": datetime.now().strftime("%Y-%m"),
                "budget": total_budget,
                "spent": total_spent,
                "remaining": remaining,
                "categories": categories,
            }

            logger.info(
                "budget_status_scraped_successfully",
                budget=total_budget,
                spent=total_spent,
                remaining=remaining,
            )

            return result

        except Exception as e:
            logger.error(
                "budget_scraping_failed",
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(f"Failed to scrape budget status: {e}") from e

        finally:
            await page.close()

    async def check_health(self) -> dict[str, Any]:
        """Check health of browser and session.

        Returns:
            Dictionary containing:
                - browser_status: Browser health status (str)
                - session_valid: Whether session is valid (bool)
                - checked_at: ISO 8601 timestamp string

        Raises:
            ScraperError: If health check fails.
        """
        logger.info("checking_health")

        try:
            # Check if browser context is available
            context = await self.browser.get_context()
            browser_status = "ok" if context else "unavailable"

            # Check session validity
            session_valid = await self.auth.is_session_valid()

            result = {
                "browser_status": browser_status,
                "session_valid": session_valid,
                "checked_at": self._get_current_timestamp(),
            }

            logger.info(
                "health_check_completed",
                browser_status=browser_status,
                session_valid=session_valid,
            )

            return result

        except Exception as e:
            logger.error(
                "health_check_failed",
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(f"Health check failed: {e}") from e

    async def update_manual_account_balance(
        self, mf_display_name: str, amount_jpy: int, *, currency: str = "MYR"
    ) -> None:
        """Update a manual account balance on MoneyForward ME.

        Flow:
        1. Navigate to /accounts to find the manual account link by display name
        2. Extract the account's hash ID URL (e.g., /accounts/show_manual/{hash})
        3. Navigate to the account detail page
        4. Use the rollover (残高修正) form to set the new balance

        Args:
            mf_display_name: Display name of the account on MoneyForward ME.
            amount_jpy: New balance in JPY.
            currency: Foreign currency code (e.g., "MYR", "USD").

        Raises:
            ScraperError: If the update operation fails.
        """
        logger.info(
            "updating_manual_account_balance",
            mf_display_name=mf_display_name,
            amount_jpy=amount_jpy,
        )

        await self.auth.ensure_authenticated()

        page = await self.browser.new_page()
        try:
            # Step 1: Go to accounts list to find the manual account URL
            await self._navigate_and_wait(page, "https://moneyforward.com/accounts")

            # Step 2: Find the link matching the display name
            account_link = page.locator(
                f'a[href*="/accounts/show_manual/"]:has-text("{mf_display_name}")'
            )
            count = await account_link.count()

            if count == 0:
                await page.screenshot(
                    path="/tmp/manual_accounts_not_found.png", full_page=True
                )
                raise ScraperError(
                    f"Account '{mf_display_name}' not found on accounts page. "
                    "Check /tmp/manual_accounts_not_found.png for page state."
                )

            # Get the account URL and navigate
            account_url = await account_link.first.get_attribute("href")
            logger.debug("account_url_found", url=account_url)

            await account_link.first.click()
            await page.wait_for_load_state("networkidle")

            await page.screenshot(
                path="/tmp/manual_account_detail.png", full_page=True
            )

            # Step 3: Check if an existing asset entry exists for this account
            # Each entry has a "change" button (btn-asset-action linking to a modal)
            change_btn = page.locator(
                'a.btn-asset-action:not([data-method="delete"])'
            )
            has_existing = await change_btn.count() > 0

            if has_existing:
                # Update existing entry via its edit modal
                logger.debug("updating_existing_entry", mf_display_name=mf_display_name)
                await change_btn.first.click()
                await page.wait_for_timeout(500)

                # The edit modal has the same form fields as the new modal
                value_input = page.locator(
                    '.modal.in input[name="user_asset_det[value]"],'
                    ' .modal.show input[name="user_asset_det[value]"]'
                )
                await value_input.wait_for(state="visible", timeout=5000)
                await value_input.clear()
                await value_input.fill(str(amount_jpy))

                submit_btn = page.locator(
                    '.modal.in input[type="submit"],'
                    ' .modal.show input[type="submit"]'
                )
                await submit_btn.first.click()
                await page.wait_for_load_state("networkidle")
            else:
                # Add new asset entry via modal
                logger.debug("creating_new_entry", mf_display_name=mf_display_name)
                await page.evaluate('$("#modal_asset_new").modal("show")')
                await page.wait_for_timeout(500)

                # Select asset subclass: "外貨預金" (id=3)
                asset_type = self.selectors["manual_accounts"].get(
                    "default_asset_subclass_id", "3"
                )
                subclass_select = page.locator(
                    '#modal_asset_new select[name="user_asset_det[asset_subclass_id]"]'
                )
                await subclass_select.wait_for(state="visible", timeout=5000)
                await subclass_select.select_option(value=asset_type)

                # Fill name
                name_input = page.locator(
                    '#modal_asset_new input[name="user_asset_det[name]"]'
                )
                await name_input.fill(f"{mf_display_name} ({currency})")

                # Fill amount
                value_input = page.locator(
                    '#modal_asset_new input[name="user_asset_det[value]"]'
                )
                await value_input.fill(str(amount_jpy))

                # Submit
                submit_btn = page.locator(
                    '#modal_asset_new input[type="submit"]'
                )
                await submit_btn.first.click()
                await page.wait_for_load_state("networkidle")

            await page.screenshot(
                path="/tmp/manual_account_saved.png", full_page=True
            )

            logger.info(
                "manual_account_balance_updated",
                mf_display_name=mf_display_name,
                amount_jpy=amount_jpy,
            )

        except ScraperError:
            raise
        except Exception as e:
            logger.error(
                "manual_account_update_failed",
                mf_display_name=mf_display_name,
                error=str(e),
                exc_info=True,
            )
            raise ScraperError(
                f"Failed to update manual account '{mf_display_name}': {e}"
            ) from e

        finally:
            await page.close()

    async def _navigate_and_wait(self, page: Page, url: str) -> None:
        """Navigate to URL and wait for network idle.

        Args:
            page: The page to navigate.
            url: The URL to navigate to.

        Raises:
            Exception: If navigation fails.
        """
        logger.debug("navigating_to_url", url=url)
        await page.goto(url, wait_until="networkidle")
        logger.debug("navigation_complete", url=url)

    async def _extract_text(self, page: Page, selector: str) -> str | None:
        """Extract text content from an element.

        Args:
            page: The page to extract from.
            selector: CSS selector for the element.

        Returns:
            Text content or None if element not found.
        """
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                return text.strip()
            return None
        except Exception as e:
            logger.warning(
                "text_extraction_failed",
                selector=selector,
                error=str(e),
            )
            return None

    def _parse_currency(self, text: str) -> int:
        """Parse currency string to integer.

        Converts strings like "¥1,234,567" or "-¥12,345" to integers.

        Args:
            text: Currency string to parse.

        Returns:
            Integer amount in JPY.
        """
        # Remove currency symbols, commas, whitespace, and Japanese text
        cleaned = re.sub(r"[¥円,\s]", "", text)
        # Extract number portion (handles "資産総額：4703541" etc.)
        match = re.search(r"-?\d+", cleaned)
        if match:
            cleaned = match.group(0)
        else:
            cleaned = ""

        # Handle empty or invalid strings
        if not cleaned or cleaned == "-":
            return 0

        try:
            return int(cleaned)
        except ValueError:
            logger.warning("currency_parse_failed", text=text)
            return 0

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO 8601 format with JST timezone.

        Returns:
            ISO 8601 timestamp string.
        """
        jst = timezone(timedelta(hours=9))
        return datetime.now(jst).isoformat()
