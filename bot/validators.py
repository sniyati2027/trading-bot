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

# Binance Futures symbols: uppercase letters only, 2-20 chars
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

# ONLY MARKET and LIMIT are supported
_SUPPORTED_TYPES = {OrderType.MARKET, OrderType.LIMIT}


def validate_order_type(raw: str) -> OrderType:
    """Parse and validate order type."""
    normalised = raw.strip().upper()

    try:
        order_type = OrderType(normalised)
    except ValueError:
        raise ValidationError(
            f"Invalid order type: '{raw}'.",
            details="Supported types: MARKET, LIMIT",
        )

    if order_type not in _SUPPORTED_TYPES:
        raise ValidationError(
            f"Order type '{order_type.value}' is not supported by this bot.",
            details="Supported types: MARKET, LIMIT",
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

    # Warn about excessive precision
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

    # LIMIT orders require price
    if order_type == OrderType.LIMIT:
        if price is None:
            raise ValidationError(
                "LIMIT orders require a --price argument.",
                details="Example: --type LIMIT --price 29500.00",
            )

    # MARKET orders should not include price
    if order_type == OrderType.MARKET:
        if price is not None:
            raise ValidationError(
                "MARKET orders should not include a price.",
                details="Remove the --price argument for MARKET orders.",
            )

    # stop_price is no longer supported
    if stop_price is not None:
        raise ValidationError(
            "STOP_MARKET orders are not supported.",
            details="Only MARKET and LIMIT orders are allowed.",
        )