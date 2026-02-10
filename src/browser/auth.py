"""Authentication management for MoneyForward ME.

This module handles login, email OTP, account selector, session validation,
and automatic re-authentication for MoneyForward ME.

Login flow: Email page → Password page → Email OTP (risk-based) → Account Selector → Dashboard
"""

import asyncio
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import Page

from src.browser.context import BrowserManager
from src.config import settings

logger = structlog.get_logger(__name__)

OTP_CODE_FILE = Path("/tmp/mf-otp-code.txt")


class AuthenticationError(Exception):
    """Raised when authentication fails after all retries."""

    pass


class AuthManager:
    """Manages authentication and session state for MoneyForward ME.

    Handles the complete login flow including:
    1. Email entry (separate page)
    2. Password entry (separate page, uses JS click to bypass overlay)
    3. Email OTP (risk-based, reads code from /tmp/mf-otp-code.txt)
    4. Account selector (auto-selects first account)
    """

    def __init__(self, browser: BrowserManager, selectors: dict[str, Any]) -> None:
        self.browser = browser
        self.selectors = selectors["auth"]
        self._max_retries = 3
        self._retry_delays = [5, 15, 45]

    async def login(self) -> bool:
        """Perform full login flow with retry logic.

        Returns:
            True if login succeeds.

        Raises:
            AuthenticationError: If login fails after all retries.
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info("login_attempt_started", attempt=attempt)

                page = await self.browser.new_page()
                try:
                    await page.goto(self.selectors["login_url"], wait_until="networkidle")
                    logger.debug("navigated_to_login_page", url=page.url)

                    # Step 1: Enter email
                    await self._enter_email(page)

                    # Step 2: Enter password
                    await self._enter_password(page)

                    # Step 3: Handle email OTP if required
                    await self._handle_email_otp(page)

                    # Step 4: Handle account selector if shown
                    await self._handle_account_selector(page)

                    # Verify login success
                    is_logged_in = await self.is_logged_in(page)
                    if is_logged_in:
                        logger.info("login_successful", attempt=attempt)
                        return True
                    else:
                        logger.warning("login_verification_failed", attempt=attempt, url=page.url)

                finally:
                    await page.close()

            except Exception as e:
                logger.warning("login_attempt_failed", attempt=attempt, error=str(e))

                if attempt < self._max_retries:
                    delay = self._retry_delays[attempt - 1]
                    logger.info("retrying_login", delay_seconds=delay)
                    await asyncio.sleep(delay)
                else:
                    raise AuthenticationError(
                        f"Login failed after {self._max_retries} attempts: {e}"
                    ) from e

        raise AuthenticationError(f"Login failed after {self._max_retries} attempts")

    async def is_session_valid(self) -> bool:
        """Check if the current session is still valid."""
        page = await self.browser.new_page()
        try:
            await page.goto("https://moneyforward.com/bs/portfolio", wait_until="networkidle")
            is_valid = await self.is_logged_in(page)
            logger.info("session_validity_checked", is_valid=is_valid)
            return is_valid
        except Exception as e:
            logger.warning("session_validation_error", error=str(e))
            return False
        finally:
            await page.close()

    async def ensure_authenticated(self) -> None:
        """Ensure the user is authenticated, logging in if necessary."""
        is_valid = await self.is_session_valid()
        if not is_valid:
            logger.info("session_invalid_reauth_required")
            await self.login()

    async def is_logged_in(self, page: Page) -> bool:
        """Check if we're currently logged in."""
        try:
            current_url = page.url
            if "moneyforward.com" in current_url and "id.moneyforward.com" not in current_url:
                return True
            return False
        except Exception:
            return False

    async def _enter_email(self, page: Page) -> None:
        """Enter email on the login page."""
        logger.debug("entering_email")
        email_input = self.selectors["email_input"]
        await page.wait_for_selector(email_input, timeout=10000)

        # Type with human-like delay to avoid bot detection
        await page.fill(email_input, "")
        await page.type(email_input, settings.mf_email, delay=50)

        # Use JS click to bypass overlay interception
        await page.evaluate(f"document.querySelector('{self.selectors['submit_button']}').click()")
        await page.wait_for_load_state("networkidle")
        logger.debug("email_entered", url=page.url)

    async def _enter_password(self, page: Page) -> None:
        """Enter password on the password page."""
        logger.debug("entering_password")
        password_input = self.selectors["password_input"]
        await page.wait_for_selector(password_input, timeout=10000)

        # Type with human-like delay
        await page.fill(password_input, "")
        await page.type(password_input, settings.mf_password.get_secret_value(), delay=50)

        # Use JS click to bypass overlay interception
        await page.evaluate(f"document.querySelector('{self.selectors['submit_button']}').click()")
        await page.wait_for_load_state("networkidle")
        logger.debug("password_entered", url=page.url)

    async def _handle_email_otp(self, page: Page) -> None:
        """Handle email OTP if required (risk-based additional auth).

        Waits for OTP code to be written to /tmp/mf-otp-code.txt.
        """
        # Check if we're on the OTP page
        if "email_otp" not in page.url:
            logger.debug("otp_not_required")
            return

        logger.info("otp_required", url=page.url)

        # Clean up any previous OTP file
        if OTP_CODE_FILE.exists():
            OTP_CODE_FILE.unlink()

        logger.info("otp_waiting_for_code", file=str(OTP_CODE_FILE))

        # Wait for OTP code file (up to 120 seconds)
        otp_code = None
        for _ in range(120):
            if OTP_CODE_FILE.exists():
                otp_code = OTP_CODE_FILE.read_text().strip()
                if otp_code:
                    break
            await asyncio.sleep(1)

        if not otp_code:
            raise AuthenticationError("OTP code not provided within 120 seconds")

        logger.info("otp_code_received", code_length=len(otp_code))

        # Clean up
        OTP_CODE_FILE.unlink(missing_ok=True)

        # Enter OTP
        otp_input = self.selectors.get("otp_input", 'input[name="mfid_user[code]"]')
        await page.wait_for_selector(otp_input, timeout=5000)
        await page.fill(otp_input, otp_code)

        otp_submit = self.selectors.get("otp_submit", 'input[type="submit"]')
        await page.click(otp_submit)
        await page.wait_for_load_state("networkidle")

        # Check if OTP was accepted
        if "email_otp" in page.url:
            body_text = await page.inner_text("body")
            if "誤っています" in body_text:
                raise AuthenticationError("OTP code was incorrect")

        logger.info("otp_success", url=page.url)

    async def _handle_account_selector(self, page: Page) -> None:
        """Handle account selector page if shown."""
        if "account_selector" not in page.url:
            logger.debug("account_selector_not_shown")
            return

        logger.info("account_selector_detected")

        # Click the first account (current account)
        try:
            # Look for the account email link
            account_link = await page.query_selector(f'a[href*="sign_in"]')
            if not account_link:
                # Try clicking the first account option
                account_link = await page.query_selector('.account-list a, [data-testid="account"]')

            if account_link:
                await account_link.click()
            else:
                # Fallback: click any link containing the user's email
                await page.click(f'text={settings.mf_email}')

            await page.wait_for_load_state("networkidle")
            logger.info("account_selected", url=page.url)
        except Exception as e:
            logger.warning("account_selector_click_failed", error=str(e))
            # Try JS navigation as fallback
            await page.evaluate("document.querySelector('a').click()")
            await page.wait_for_load_state("networkidle")
