"""
CLI entry point for the Binance Futures Trading Bot.

Two modes of operation:
  1. Direct command (argparse) — scriptable, CI-friendly
  2. Interactive menu   (--interactive) — guided prompts for humans

Rich is used for coloured output and tables.
All business logic delegates to bot.orders and bot.validators.
"""

import argparse
import sys
from decimal import Decimal
from typing import Optional

# Rich for beautiful terminal output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.rule import Rule
    _RICH = True
except ImportError:
    _RICH = False

from bot.config import load_config
from bot.client import BinanceClient
from bot.orders import OrderManager
from bot.models import OrderResponse, OrderSide, OrderType, TimeInForce
from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_order_params,
    validate_time_in_force,
)
from bot.exceptions import TradingBotError, ValidationError, ConfigurationError
from bot.logging_config import setup_logging, get_logger

logger = get_logger(__name__)
console = Console() if _RICH else None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print(msg: str, style: str = "") -> None:
    if _RICH and console:
        console.print(msg, style=style)
    else:
        print(msg)


def _print_order_request_summary(
    symbol: str, side: str, order_type: str,
    quantity: str, price: Optional[str], stop_price: Optional[str]
) -> None:
    """Print a clean order summary before sending."""
    if _RICH and console:
        table = Table(title="Order Request", box=box.ROUNDED, show_header=False,
                      border_style="cyan", title_style="bold cyan")
        table.add_column("Field", style="bold", width=16)
        table.add_column("Value")

        side_style = "green" if side.upper() == "BUY" else "red"
        table.add_row("Symbol",     f"[bold]{symbol}[/bold]")
        table.add_row("Side",       f"[bold {side_style}]{side.upper()}[/bold {side_style}]")
        table.add_row("Type",       order_type.upper())
        table.add_row("Quantity",   quantity)
        if price:
            table.add_row("Price", price)
        if stop_price:
            table.add_row("Stop Price", stop_price)

        console.print(table)
    else:
        print(f"\n--- Order Request ---")
        print(f"Symbol    : {symbol}")
        print(f"Side      : {side.upper()}")
        print(f"Type      : {order_type.upper()}")
        print(f"Quantity  : {quantity}")
        if price:
            print(f"Price     : {price}")
        if stop_price:
            print(f"Stop Price: {stop_price}")


def _print_order_response(response: OrderResponse) -> None:
    """Print a rich order response table."""
    if _RICH and console:
        status_colors = {
            "FILLED": "bold green",
            "NEW": "bold cyan",
            "PARTIALLY_FILLED": "yellow",
            "CANCELED": "red",
            "REJECTED": "bold red",
        }
        status_style = status_colors.get(response.status, "white")

        table = Table(title="Order Response", box=box.ROUNDED,
                      show_header=False, border_style="green", title_style="bold green")
        table.add_column("Field", style="bold", width=18)
        table.add_column("Value")

        table.add_row("Order ID",     str(response.order_id))
        table.add_row("Client OID",   response.client_order_id)
        table.add_row("Symbol",       response.symbol)
        table.add_row("Side",         response.side)
        table.add_row("Type",         response.order_type)
        table.add_row("Status",       f"[{status_style}]{response.status}[/{status_style}]")
        table.add_row("Orig Qty",     response.orig_qty)
        table.add_row("Executed Qty", response.executed_qty)
        table.add_row("Avg Price",    response.display_price)

        console.print(table)

        if response.status == "FILLED":
            console.print(Panel(
                "[bold green]✓ Order filled successfully[/bold green]",
                border_style="green",
            ))
        elif response.status == "NEW":
            console.print(Panel(
                "[bold cyan]⟳ Order placed — resting on the book[/bold cyan]",
                border_style="cyan",
            ))
    else:
        print(f"\n--- Order Response ---")
        print(f"Order ID    : {response.order_id}")
        print(f"Symbol      : {response.symbol}")
        print(f"Status      : {response.status}")
        print(f"Executed Qty: {response.executed_qty}")
        print(f"Avg Price   : {response.display_price}")
        print(f"\nSUCCESS: Order placed (ID {response.order_id})")


def _print_error(exc: Exception) -> None:
    if _RICH and console:
        console.print(Panel(
            f"[bold red]✗ Error:[/bold red] {exc}",
            border_style="red",
            title="[red]Failed[/red]",
        ))
    else:
        print(f"\nERROR: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core order dispatch
# ---------------------------------------------------------------------------

def execute_order(
    manager: OrderManager,
    symbol: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: Decimal,
    price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    time_in_force: TimeInForce = TimeInForce.GTC,
    reduce_only: bool = False,
) -> OrderResponse:
    """Route to the correct order method based on order_type."""
    if order_type == OrderType.MARKET:
        return manager.place_market_order(
            symbol=symbol, side=side, quantity=quantity, reduce_only=reduce_only
        )
    elif order_type == OrderType.LIMIT:
        return manager.place_limit_order(
            symbol=symbol, side=side, quantity=quantity,
            price=price, time_in_force=time_in_force, reduce_only=reduce_only
        )

    else:
        raise ValidationError(f"Order type {order_type.value} routing not implemented.")


# ---------------------------------------------------------------------------
# Interactive menu (bonus UX)
# ---------------------------------------------------------------------------

def run_interactive(manager: OrderManager) -> None:
    """Guided interactive mode — collects params via prompts."""
    if not _RICH:
        _print("Install rich for interactive mode: pip install rich")
        return

    console.print(Rule("[bold cyan]Binance Futures Testnet — Interactive Order Entry[/bold cyan]"))
    console.print()

    # Symbol
    while True:
        raw_symbol = Prompt.ask("[cyan]Symbol[/cyan]", default="BTCUSDT")
        try:
            symbol = validate_symbol(raw_symbol)
            break
        except ValidationError as e:
            console.print(f"[red]{e}[/red]")

    # Fetch current price for context
    try:
        current_price = manager._client.get_ticker_price(symbol)
        console.print(f"  [dim]Current mark price: {current_price}[/dim]")
    except Exception:
        current_price = None

    # Side
    while True:
        raw_side = Prompt.ask("[cyan]Side[/cyan]", choices=["BUY", "SELL"])
        try:
            side = validate_side(raw_side)
            break
        except ValidationError as e:
            console.print(f"[red]{e}[/red]")

    # Order type
    while True:
        raw_type = Prompt.ask(
            "[cyan]Order type[/cyan]",
            choices=["MARKET", "LIMIT"],
            default="MARKET",
        )
        try:
            order_type = validate_order_type(raw_type)
            break
        except ValidationError as e:
            console.print(f"[red]{e}[/red]")

    # Quantity
    while True:
        raw_qty = Prompt.ask("[cyan]Quantity[/cyan]", default="0.001")
        try:
            quantity = validate_quantity(raw_qty)
            break
        except ValidationError as e:
            console.print(f"[red]{e}[/red]")

    # Price (if needed)
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None

    if order_type == OrderType.LIMIT:
        while True:
            default_price = current_price or "29000"
            raw_price = Prompt.ask("[cyan]Limit price[/cyan]", default=default_price)
            try:
                price = validate_price(raw_price)
                break
            except ValidationError as e:
                console.print(f"[red]{e}[/red]")


    # Summary + confirm
    console.print()
    _print_order_request_summary(
        symbol=symbol, side=raw_side, order_type=raw_type,
        quantity=str(quantity),
        price=str(price) if price else None,
        stop_price=str(stop_price) if stop_price else None,
    )
    console.print()

    if not Confirm.ask("[bold yellow]Send this order?[/bold yellow]"):
        console.print("[dim]Cancelled.[/dim]")
        return

    try:
        response = execute_order(
            manager=manager, symbol=symbol, side=side,
            order_type=order_type, quantity=quantity,
            price=price, stop_price=stop_price,
        )
        _print_order_response(response)
    except TradingBotError as exc:
        _print_error(exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description=(
            "Binance Futures Testnet Trading Bot\n"
            "Place MARKET, LIMIT orders from the command line."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  Market buy 0.001 BTC:
    python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

  Limit sell 0.002 ETH at $1800:
    python cli.py --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.002 --price 1800

  Interactive mode:
    python cli.py --interactive
        """,
    )

    # Target
    parser.add_argument("--symbol",     type=str, help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--side",       type=str, help="BUY or SELL")
    parser.add_argument("--type",       type=str, dest="order_type",
                        help="MARKET | LIMIT ")
    parser.add_argument("--quantity",   type=str, help="Order quantity")
    parser.add_argument("--price",      type=str, default=None,
                        help="Limit price (required for LIMIT orders)")
    parser.add_argument("--tif",        type=str, default="GTC", dest="time_in_force",
                        help="Time-in-force: GTC (default) | IOC | FOK | GTX")
    parser.add_argument("--reduce-only", action="store_true", dest="reduce_only",
                        help="Mark order as reduce-only (closes position only)")

    # Modes
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Launch interactive guided order entry")
    parser.add_argument("--testnet",     action="store_true", default=True,
                        help="Use Binance Futures Testnet (default: true)")
    parser.add_argument("--mainnet",     action="store_true", default=False,
                        help="Use mainnet (CAUTION: real funds)")

    # Logging
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Console log level (default: INFO)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress all console output (log to file only)")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Logging setup (first thing, before anything that might log)
    setup_logging(log_level=args.log_level, quiet=args.quiet)

    # Config / credentials
    try:
        use_testnet = not args.mainnet
        config = load_config(testnet=use_testnet)
    except ConfigurationError as exc:
        _print_error(exc)
        _print("\n[yellow]Hint:[/yellow] Copy .env.example to .env and fill in your API credentials.", "yellow")
        sys.exit(1)

    # Warn loudly if using mainnet
    if not use_testnet and _RICH and console:
        console.print(Panel(
            "[bold red]⚠ WARNING: Connected to MAINNET — real funds at risk![/bold red]",
            border_style="red",
        ))

    client  = BinanceClient(config)
    manager = OrderManager(client)

    # --------------- Interactive mode ---------------
    if args.interactive:
        run_interactive(manager)
        return

    # --------------- Validate required args ---------------
    required = ["symbol", "side", "order_type", "quantity"]
    missing  = [f"--{r.replace('_', '-')}" for r in required if not getattr(args, r, None)]
    if missing:
        parser.print_usage()
        _print(
            f"\n[red]Missing required arguments:[/red] {', '.join(missing)}\n"
            f"Run with [cyan]--interactive[/cyan] for guided mode.",
        )
        sys.exit(1)

    # --------------- Validate & parse ---------------
    try:
        symbol     = validate_symbol(args.symbol)
        side       = validate_side(args.side)
        order_type = validate_order_type(args.order_type)
        quantity   = validate_quantity(args.quantity)
        price      = validate_price(args.price) if args.price else None
        stop_price = validate_price(args.stop_price) if args.stop_price else None
        tif        = validate_time_in_force(args.time_in_force)
        validate_order_params(order_type, price, stop_price)
    except ValidationError as exc:
        _print_error(exc)
        sys.exit(1)

    # --------------- Print request summary ---------------
    _print_order_request_summary(
        symbol=symbol, side=args.side, order_type=args.order_type,
        quantity=str(quantity),
        price=str(price) if price else None,
        stop_price=str(stop_price) if stop_price else None,
    )

    if _RICH and console:
        console.print()

    # --------------- Send order ---------------
    try:
        response = execute_order(
            manager=manager, symbol=symbol, side=side,
            order_type=order_type, quantity=quantity,
            price=price, stop_price=stop_price, time_in_force=tif,
            reduce_only=args.reduce_only,
        )
    except TradingBotError as exc:
        _print_error(exc)
        logger.error("Order failed", extra={"error": str(exc)})
        sys.exit(1)

    # --------------- Print response ---------------
    _print_order_response(response)


if __name__ == "__main__":
    main()