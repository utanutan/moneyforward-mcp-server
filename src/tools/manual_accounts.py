"""MCP tools for managing manual accounts with foreign currency support.

This module provides tools for listing and updating manual accounts
on MoneyForward ME, with MYR to JPY currency conversion.
"""

from typing import Any

import httpx
import structlog

from src.config import load_accounts
from src.tools.common import build_error_response, build_success_response

logger = structlog.get_logger(__name__)

EXCHANGE_RATE_API_URL = "https://open.er-api.com/v6/latest/MYR"


async def list_manual_accounts() -> dict[str, Any]:
    """List manual accounts from accounts.yaml configuration.

    Returns:
        Standardized response containing account list with name, type, and currency.
    """
    logger.info("list_manual_accounts_called")

    try:
        accounts = load_accounts()
        account_list = [
            {
                "name": acc["name"],
                "type": acc["type"],
                "currency": acc["currency"],
                "mf_display_name": acc["mf_display_name"],
            }
            for acc in accounts
        ]

        return build_success_response(
            {"accounts": account_list, "count": len(account_list)},
            source="config",
            cached=False,
        )

    except FileNotFoundError as e:
        logger.error("accounts_config_not_found", error=str(e))
        return build_error_response(
            message=f"accounts.yaml not found: {e}",
            error_type="CONFIG_ERROR",
        )
    except Exception as e:
        logger.error("list_manual_accounts_failed", error=str(e), exc_info=True)
        return build_error_response(
            message=f"Failed to list manual accounts: {e}",
            error_type="CONFIG_ERROR",
        )


async def _get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Fetch exchange rate from open.er-api.com.

    Args:
        from_currency: Source currency code (e.g., "MYR").
        to_currency: Target currency code (e.g., "JPY").

    Returns:
        Exchange rate as float.

    Raises:
        RuntimeError: If API call fails or rate not found.
    """
    url = f"https://open.er-api.com/v6/latest/{from_currency}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("result") != "success":
        raise RuntimeError(f"Exchange rate API error: {data}")

    rates = data.get("rates", {})
    rate = rates.get(to_currency)
    if rate is None:
        raise RuntimeError(f"Rate not found for {to_currency} in API response")

    return float(rate)


async def update_manual_account(
    scraper: Any,
    account_name: str,
    amount_myr: float,
) -> dict[str, Any]:
    """Update a manual account balance on MoneyForward ME with MYR to JPY conversion.

    Args:
        scraper: MoneyForwardScraper instance.
        account_name: Account name as defined in accounts.yaml.
        amount_myr: Balance amount in MYR.

    Returns:
        Standardized response containing update result with conversion details.
    """
    logger.info(
        "update_manual_account_called",
        account_name=account_name,
        amount_myr=amount_myr,
    )

    try:
        # Find account in config
        accounts = load_accounts()
        target = None
        for acc in accounts:
            if acc["name"] == account_name:
                target = acc
                break

        if target is None:
            return build_error_response(
                message=f"Account '{account_name}' not found in accounts.yaml",
                error_type="ACCOUNT_NOT_FOUND",
            )

        # Get exchange rate
        rate = await _get_exchange_rate(target["currency"], "JPY")
        amount_jpy = int(amount_myr * rate)

        logger.info(
            "currency_converted",
            from_currency=target["currency"],
            amount_myr=amount_myr,
            rate=rate,
            amount_jpy=amount_jpy,
        )

        # Update on MoneyForward ME
        mf_display_name = target["mf_display_name"]
        await scraper.update_manual_account_balance(mf_display_name, amount_jpy)

        from datetime import datetime, timedelta, timezone

        jst = timezone(timedelta(hours=9))

        return build_success_response(
            {
                "account_name": account_name,
                "mf_display_name": mf_display_name,
                "amount_myr": amount_myr,
                "amount_jpy": amount_jpy,
                "exchange_rate": rate,
                "currency": target["currency"],
                "updated_at": datetime.now(jst).isoformat(),
            },
            source="scraping",
            cached=False,
        )

    except FileNotFoundError as e:
        logger.error("accounts_config_not_found", error=str(e))
        return build_error_response(
            message=f"accounts.yaml not found: {e}",
            error_type="CONFIG_ERROR",
        )
    except Exception as e:
        logger.error(
            "update_manual_account_failed",
            account_name=account_name,
            error=str(e),
            exc_info=True,
        )
        return build_error_response(
            message=f"Failed to update manual account: {e}",
            error_type="UPDATE_ERROR",
        )
