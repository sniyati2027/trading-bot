"""
Custom exception hierarchy for the trading bot.

Why a hierarchy instead of bare Exception?
- Callers can catch at the right granularity (APIError vs NetworkError)
- Error messages are self-documenting
- Makes unit-testing error paths trivial
"""

from typing import Optional


class TradingBotError(Exception):
    """Base exception. All bot errors inherit from this."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} — {self.details}"
        return self.message


# ---------------------------------------------------------------------------
# Validation errors (user input / config problems)
# ---------------------------------------------------------------------------

class ValidationError(TradingBotError):
    """Raised when user-supplied arguments fail validation."""


class ConfigurationError(TradingBotError):
    """Raised when .env / config values are missing or invalid."""


# ---------------------------------------------------------------------------
# API / network errors
# ---------------------------------------------------------------------------

class APIError(TradingBotError):
    """Base class for all Binance API errors.

    Attributes
    ----------
    status_code : HTTP status code returned by the server
    binance_code : Binance error code from the response body (e.g. -1121)
    """

    def __init__(self, message: str, status_code: int = 0, binance_code: int = 0,
                 details: Optional[str] = None):
        super().__init__(message, details)
        self.status_code = status_code
        self.binance_code = binance_code


class AuthenticationError(APIError):
    """Invalid API key / signature mismatch."""


class InsufficientFundsError(APIError):
    """Not enough margin / balance to place the order."""


class InvalidSymbolError(APIError):
    """Symbol not found or not tradeable on this market."""


class InvalidOrderError(APIError):
    """Order parameters rejected by the exchange."""


class RateLimitError(APIError):
    """Hit Binance request weight or order rate limit."""

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class NetworkError(TradingBotError):
    """Connection timeout, DNS failure, or other transport-level error."""


# ---------------------------------------------------------------------------
# Mapping from Binance error codes → typed exceptions
# Reference: https://binance-docs.github.io/apidocs/futures/en/#error-codes
# ---------------------------------------------------------------------------

_BINANCE_CODE_MAP: dict[int, type[APIError]] = {
    -1000: APIError,              # UNKNOWN
    -1100: InvalidOrderError,     # Illegal chars in parameter
    -1101: InvalidOrderError,     # Too many params
    -1102: InvalidOrderError,     # Mandatory param empty
    -1111: InvalidOrderError,     # Precision exceeds maximum
    -1121: InvalidSymbolError,    # Invalid symbol
    -2010: InvalidOrderError,     # New order rejected
    -2011: InvalidOrderError,     # Cancel rejected
    -2015: AuthenticationError,   # Invalid API-key / IP / permissions
    -2018: InsufficientFundsError, # Balance insufficient
    -2019: InsufficientFundsError, # Margin is insufficient
    -1003: RateLimitError,        # Too many requests (429)
    -1015: RateLimitError,        # Too many new orders
}


def map_api_error(binance_code: int, message: str,
                  status_code: int = 400) -> APIError:
    """
    Return the most specific APIError subclass for a given Binance code.
    Falls back to generic APIError for unrecognised codes.
    """
    exc_class = _BINANCE_CODE_MAP.get(binance_code, APIError)
    return exc_class(
        message=message,
        status_code=status_code,
        binance_code=binance_code,
    )