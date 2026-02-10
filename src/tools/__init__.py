"""MCP tools module for MoneyForward ME data access.

This module provides FastMCP tools for accessing MoneyForward ME data including:
- Total assets
- Recent transactions
- Budget status
- Account refresh
- Health check
"""

from src.tools.assets import get_total_assets
from src.tools.transactions import list_recent_transactions
from src.tools.budget import get_budget_status
from src.tools.refresh import trigger_refresh
from src.tools.health import health_check
from src.tools.manual_accounts import list_manual_accounts, update_manual_account

__all__ = [
    "get_total_assets",
    "list_recent_transactions",
    "get_budget_status",
    "trigger_refresh",
    "health_check",
    "list_manual_accounts",
    "update_manual_account",
]
