"""
Order placement logic.

This module is the "business logic" layer:
- Builds typed OrderRequest objects from validated inputs
- Delegates raw HTTP to BinanceClient
- Parses responses into typed OrderResponse objects
- Logs every action with context for auditability
"""

from decimal import Decimal
from typing import Optional

from bot.client import BinanceClient
from bot.config import ENDPOINTS
from bot.exceptions import TradingBotError
from bot.logging_config import get_logger
from bot.models import (
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderType,
    TimeInForce,
)

logger = get_logger(__name__)


class OrderManager:
    """
    High-level interface for order operations.

    All public methods log before and after the API call so the log file
    contains a complete audit trail without any extra instrumentation.
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> OrderResponse:
        """Place a MARKET order (executes immediately at best available price)."""
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
        )
        return self._place_order(request)

    def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> OrderResponse:
        """Place a LIMIT order (rests on the book until filled or cancelled)."""
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
        )
        return self._place_order(request)

    def place_stop_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        stop_price: Decimal,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> OrderResponse:
        """
        [BONUS] Place a STOP_MARKET order.

        Triggers a market order when the mark price crosses stop_price.
        Commonly used as a stop-loss.
        """
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            stop_price=stop_price,
            reduce_only=reduce_only,
            client_order_id=client_order_id,
        )
        return self._place_order(request)

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        """Return all open orders, optionally filtered by symbol."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        logger.info("Fetching open orders", extra={"symbol": symbol or "all"})
        return self._client.get(ENDPOINTS["open_orders"], params=params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order by orderId."""
        logger.info("Cancelling order", extra={"symbol": symbol, "order_id": order_id})
        result = self._client.delete(
            ENDPOINTS["cancel_order"],
            params={"symbol": symbol, "orderId": order_id},
            signed=True,
        )
        logger.info("Order cancelled", extra={"order_id": order_id, "status": result.get("status")})
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _place_order(self, request: OrderRequest) -> OrderResponse:
        """
        Core order dispatch: log → send → parse → log → return.
        Any exception from the client layer propagates up unchanged.
        """
        params = request.to_api_params()

        logger.info(
            "Placing order",
            extra={
                "symbol": request.symbol,
                "side": request.side.value,
                "type": request.order_type.value,
                "quantity": str(request.quantity),
                "price": str(request.price) if request.price else None,
                "stop_price": str(request.stop_price) if request.stop_price else None,
            },
        )

        try:
            raw = self._client.post(ENDPOINTS["new_order"], params=params, signed=True)
        except TradingBotError:
            logger.error(
                "Order placement failed",
                extra={
                    "symbol": request.symbol,
                    "side": request.side.value,
                    "type": request.order_type.value,
                },
            )
            raise

        response = OrderResponse.from_api_response(raw)

        logger.info(
            "Order placed successfully",
            extra={
                "order_id": response.order_id,
                "symbol": response.symbol,
                "side": response.side,
                "type": response.order_type,
                "status": response.status,
                "executed_qty": response.executed_qty,
                "avg_price": response.avg_price,
            },
        )

        return response