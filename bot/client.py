"""
Binance Futures API client.

Responsibilities:
- HMAC-SHA256 request signing
- HTTP session management (connection pooling)
- Automatic retry with exponential backoff for transient errors
- Response error parsing → typed exceptions
- All raw HTTP interactions live here; no business logic
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.config import Config, ENDPOINTS
from bot.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    map_api_error,
)
from bot.logging_config import get_logger

logger = get_logger(__name__)


def _build_session(max_retries: int) -> requests.Session:
    """
    Build a requests.Session with:
    - Connection pooling (reuse TCP connections)
    - Automatic retry on 502/503/504 (gateway errors, not order logic)
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST", "DELETE"],
        backoff_factor=0.5,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class BinanceClient:
    """
    Low-level Binance Futures REST client.

    Usage:
        client = BinanceClient(config)
        data = client.post("/fapi/v1/order", params={...}, signed=True)
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = _build_session(config.max_retries)
        self._session.headers.update({
            "X-MBX-APIKEY": config.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        logger.debug("BinanceClient initialised", extra={"base_url": config.base_url})

    # ------------------------------------------------------------------
    # Public HTTP methods
    # ------------------------------------------------------------------

    def get(self, endpoint: str, params: Optional[dict] = None,
            signed: bool = False) -> Any:
        return self._request("GET", endpoint, params=params, signed=signed)

    def post(self, endpoint: str, params: Optional[dict] = None,
             signed: bool = True) -> Any:
        return self._request("POST", endpoint, params=params, signed=signed)

    def delete(self, endpoint: str, params: Optional[dict] = None,
               signed: bool = True) -> Any:
        return self._request("DELETE", endpoint, params=params, signed=signed)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_server_time(self) -> int:
        """Return Binance server time in milliseconds."""
        data = self.get(ENDPOINTS["server_time"])
        return data["serverTime"]

    def get_ticker_price(self, symbol: str) -> str:
        """Return latest mark price for a symbol."""
        data = self.get(ENDPOINTS["ticker_price"], params={"symbol": symbol})
        return data["price"]

    # ------------------------------------------------------------------
    # Internal signing & dispatch
    # ------------------------------------------------------------------

    def _sign(self, params: dict) -> dict:
        """
        Add a timestamp + HMAC-SHA256 signature to the parameter dict.
        Binance requires the signature to be the *last* parameter.
        """
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self._config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        signed: bool = False,
    ) -> Any:
        """
        Execute an HTTP request, handle errors, return parsed JSON.

        Raises
        ------
        NetworkError    — timeout / connection failure
        RateLimitError  — HTTP 429 / Binance code -1003
        AuthenticationError — bad key / signature
        APIError (or subclass) — any other Binance error
        """
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{self._config.base_url}{endpoint}"

        logger.debug(
            "API request",
            extra={
                "method": method,
                "endpoint": endpoint,
                "params": {k: v for k, v in params.items()
                           if k not in ("signature", "timestamp")},
            },
        )

        try:
            if method == "GET":
                response = self._session.get(
                    url, params=params, timeout=self._config.timeout
                )
            elif method == "POST":
                response = self._session.post(
                    url, data=params, timeout=self._config.timeout
                )
            elif method == "DELETE":
                response = self._session.delete(
                    url, params=params, timeout=self._config.timeout
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        except requests.exceptions.Timeout:
            logger.error("Request timed out", extra={"url": url})
            raise NetworkError(
                "Request timed out.",
                details=f"No response from {url} within {self._config.timeout}s.",
            )
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error", extra={"url": url, "error": str(exc)})
            raise NetworkError(
                "Could not connect to the exchange.",
                details=str(exc),
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected request error", extra={"error": str(exc)})
            raise NetworkError("Unexpected network error.", details=str(exc))

        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> Any:
        """Parse and validate the HTTP response."""
        status = response.status_code

        logger.debug(
            "API response",
            extra={
                "status_code": status,
                "used_weight": response.headers.get("X-MBX-USED-WEIGHT-1M"),
            },
        )

        # Rate limit hit
        if status == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning("Rate limit hit", extra={"retry_after": retry_after})
            raise RateLimitError(
                "Rate limit exceeded.",
                retry_after=retry_after,
                status_code=status,
            )

        # Try to parse JSON regardless of status (Binance sends errors as JSON)
        try:
            data = response.json()
        except ValueError:
            logger.error("Non-JSON response", extra={"body": response.text[:200]})
            raise APIError(
                "Unexpected non-JSON response from exchange.",
                status_code=status,
                details=response.text[:200],
            )

        # Binance returns errors as {"code": <negative int>, "msg": "..."}
        if status >= 400 or (isinstance(data, dict) and "code" in data and data["code"] < 0):
            code = data.get("code", 0)
            msg  = data.get("msg", "Unknown error")
            logger.error(
                "API error response",
                extra={"binance_code": code, "binance_msg": msg, "status_code": status},
            )
            raise map_api_error(code, msg, status_code=status)

        logger.debug("API call succeeded", extra={"status_code": status})
        return data