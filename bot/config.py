"""
Configuration management.

API keys are never hardcoded — they live in a .env file (git-ignored).
This module loads them once and exposes a typed Config object.
"""

import os
from dataclasses import dataclass
from pathlib import Path

# python-dotenv loads .env automatically; gracefully absent = no-op
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False

from bot.exceptions import ConfigurationError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TESTNET_BASE_URL = "https://demo-fapi.binance.com"
MAINNET_BASE_URL = "https://fapi.binance.com"

# Binance Futures Testnet endpoints
ENDPOINTS = {
    "new_order":       "/fapi/v1/order",
    "query_order":     "/fapi/v1/order",
    "cancel_order":    "/fapi/v1/order",
    "open_orders":     "/fapi/v1/openOrders",
    "account":         "/fapi/v2/account",
    "exchange_info":   "/fapi/v1/exchangeInfo",
    "server_time":     "/fapi/v1/time",
    "ticker_price":    "/fapi/v1/ticker/price",
}

# Default request timeout (seconds)
DEFAULT_TIMEOUT = 10

# Max retries for transient errors
MAX_RETRIES = 3

# Exponential backoff base (seconds)
RETRY_BACKOFF_BASE = 0.5


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    api_key: str
    api_secret: str
    base_url: str = TESTNET_BASE_URL
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = MAX_RETRIES

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ConfigurationError(
                "BINANCE_API_KEY is not set.",
                details="Add it to your .env file or export it as an environment variable.",
            )
        if not self.api_secret:
            raise ConfigurationError(
                "BINANCE_API_SECRET is not set.",
                details="Add it to your .env file or export it as an environment variable.",
            )


def load_config(testnet: bool = True) -> Config:
    """
    Load API credentials from environment variables.

    Order of precedence:
      1. Existing environment variables (e.g. exported in shell)
      2. .env file in project root (loaded by dotenv above)
    """
    api_key    = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    base_url   = TESTNET_BASE_URL if testnet else MAINNET_BASE_URL

    return Config(api_key=api_key, api_secret=api_secret, base_url=base_url)