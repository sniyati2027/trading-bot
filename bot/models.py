"""
Typed dataclasses for all request/response structures.
Keeps the codebase self-documenting and IDE-friendly.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"          # Stop-Market  (bonus)
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"


class TimeInForce(str, Enum):
    GTC = "GTC"   # Good Till Cancel
    IOC = "IOC"   # Immediate Or Cancel
    FOK = "FOK"   # Fill Or Kill
    GTX = "GTX"   # Post Only


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

@dataclass
class OrderRequest:
    """Validated, typed order request before it hits the API."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None           # Required for LIMIT / STOP
    stop_price: Optional[Decimal] = None      # Required for STOP orders (bonus)
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    client_order_id: Optional[str] = None

    def to_api_params(self) -> dict:
        """Convert to Binance API parameter dict (no None values)."""
        params: dict = {
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": str(self.quantity),
        }
        if self.order_type in (OrderType.LIMIT,):
            params["price"] = str(self.price)
            params["timeInForce"] = self.time_in_force.value
        if self.order_type in (OrderType.STOP, OrderType.STOP_MARKET, OrderType.TAKE_PROFIT):
            params["stopPrice"] = str(self.stop_price)
            if self.price:
                params["price"] = str(self.price)
                params["timeInForce"] = self.time_in_force.value
        if self.reduce_only:
            params["reduceOnly"] = "true"
        if self.client_order_id:
            params["newClientOrderId"] = self.client_order_id
        return params


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

@dataclass
class OrderResponse:
    """Parsed, typed response from the Binance API."""
    order_id: int
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    price: str
    avg_price: str
    orig_qty: str
    executed_qty: str
    cum_quote: str
    time_in_force: str
    transact_time: int
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api_response(cls, data: dict) -> "OrderResponse":
        """Build an OrderResponse from the raw Binance API dict."""
        return cls(
            order_id=data.get("orderId", 0),
            client_order_id=data.get("clientOrderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            status=data.get("status", ""),
            price=data.get("price", "0"),
            avg_price=data.get("avgPrice", data.get("price", "0")),
            orig_qty=data.get("origQty", "0"),
            executed_qty=data.get("executedQty", "0"),
            cum_quote=data.get("cumQuote", "0"),
            time_in_force=data.get("timeInForce", ""),
            transact_time=data.get("transactTime", 0),
            raw=data,
        )

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED.value

    @property
    def display_price(self) -> str:
        """Return avg price if available, otherwise limit price."""
        avg = self.avg_price.rstrip("0").rstrip(".")
        if avg and avg != "0":
            return avg
        p = self.price.rstrip("0").rstrip(".")
        return p if p else "market"