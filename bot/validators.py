"""
Input validation layer.

All validation lives here — the CLI and order logic stay clean.
Each function raises ValidationError with an actionable message.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from bot.exceptions import ValidationError
from bot.models import OrderSide, OrderType, TimeInForce


# ---------------------------------------------------------------------------
# Symbol
# ---------------------------------------------------------------------------

# Binance Futures symbols: uppercase letters only, 2-20 chars, ends with USDT/BUSD/USD
_SYMBOL_RE = re.compile(r"^[A-Z]{2,20}$")


def validate_symbol(raw: str) -> str:
    """
    Normalise and validate a trading symbol.

    Returns the upper-cased symbol on success, raises ValidationError otherwise.
    """
    symbol = raw.strip().upper()
    if not symbol:
        raise ValidationError("Symbol cannot be empty.")
    if not _SYMBOL_RE.match(symbol):
        raise ValidationError(
            f"Invalid symbol: '{symbol}'.",
            details="Symbols must be 2–20 uppercase letters, e.g. BTCUSDT, ETHUSDT.",
        )
    return symbol


# ---------------------------------------------------------------------------
# Side
# ---------------------------------------------------------------------------

def validate_side(raw: str) -> OrderSide:
    """Parse and validate BUY / SELL."""
    normalised = raw.strip().upper()
    try:
        return OrderSide(normalised)
    except ValueError:
        raise ValidationError(
            f"Invalid side: '{raw}'.",
            details=f"Must be one of: {', '.join(s.value for s in OrderSide)}",
        )


# ---------------------------------------------------------------------------
# Order type
# ---------------------------------------------------------------------------

_SUPPORTED_TYPES = {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_MARKET}


def validate_order_type(raw: str) -> OrderType:
    """Parse and validate order type."""
    normalised = raw.strip().upper()
    # Accept common aliases
    aliases = {"STOP": "STOP_MARKET", "STOP-LIMIT": "STOP_MARKET"}
    normalised = aliases.get(normalised, normalised)
    try:
        order_type = OrderType(normalised)
    except ValueError:
        raise ValidationError(
            f"Invalid order type: '{raw}'.",
            details=f"Supported types: {', '.join(t.value for t in _SUPPORTED_TYPES)}",
        )
    if order_type not in _SUPPORTED_TYPES:
        raise ValidationError(
            f"Order type '{order_type.value}' is not supported by this bot.",
            details=f"Supported types: {', '.join(t.value for t in _SUPPORTED_TYPES)}",
        )
    return order_type


# ---------------------------------------------------------------------------
# Quantity
# ---------------------------------------------------------------------------

def validate_quantity(raw: str) -> Decimal:
    """
    Parse and validate order quantity.
    Must be a positive number with at most 3 decimal places.
    """
    try:
        qty = Decimal(str(raw).strip())
    except InvalidOperation:
        raise ValidationError(
            f"Invalid quantity: '{raw}'.",
            details="Quantity must be a positive number, e.g. 0.001",
        )
    if qty <= 0:
        raise ValidationError(
            "Quantity must be greater than zero.",
            details=f"Got: {qty}",
        )
    # Warn about excessive precision (Binance silently rejects it)
    sign, digits, exponent = qty.as_tuple()
    if exponent < -3:
        raise ValidationError(
            f"Quantity '{qty}' has too many decimal places.",
            details="Binance Futures supports at most 3 decimal places for most pairs.",
        )
    return qty


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

def validate_price(raw: str, allow_zero: bool = False) -> Decimal:
    """
    Parse and validate a price value.
    """
    try:
        price = Decimal(str(raw).strip())
    except InvalidOperation:
        raise ValidationError(
            f"Invalid price: '{raw}'.",
            details="Price must be a positive number, e.g. 30000.50",
        )
    if not allow_zero and price <= 0:
        raise ValidationError(
            "Price must be greater than zero.",
            details=f"Got: {price}",
        )
    return price


# ---------------------------------------------------------------------------
# Time-in-force
# ---------------------------------------------------------------------------

def validate_time_in_force(raw: str) -> TimeInForce:
    normalised = raw.strip().upper()
    try:
        return TimeInForce(normalised)
    except ValueError:
        raise ValidationError(
            f"Invalid time-in-force: '{raw}'.",
            details=f"Must be one of: {', '.join(t.value for t in TimeInForce)}",
        )


# ---------------------------------------------------------------------------
# Cross-field validation
# ---------------------------------------------------------------------------

def validate_order_params(
    order_type: OrderType,
    price: Optional[Decimal],
    stop_price: Optional[Decimal],
) -> None:
    """
    Validate that required fields are present for a given order type.
    Raises ValidationError if any required field is missing.
    """
    if order_type == OrderType.LIMIT:
        if price is None:
            raise ValidationError(
                "LIMIT orders require a --price argument.",
                details="Example: --type LIMIT --price 29500.00",
            )
    if order_type == OrderType.STOP_MARKET:
        if stop_price is None:
            raise ValidationError(
                "STOP_MARKET orders require a --stop-price argument.",
                details="Example: --type STOP_MARKET --stop-price 28000.00",
            )