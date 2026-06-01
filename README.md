# Binance Futures Trading Bot

A production-grade Python trading bot for Binance Futures Testnet (USDT-M).  
Places Market, Limit, and Stop-Market orders via a clean CLI with rich terminal output and structured JSON logging.

---

## Features

| Feature | Detail |
|---|---|
| Order types | MARKET · LIMIT · STOP_MARKET (bonus) |
| Sides | BUY · SELL |
| CLI modes | Direct args (scriptable) and `--interactive` guided mode |
| Output | Rich coloured tables with status-aware formatting |
| Logging | Structured JSON to file + coloured console via `rich` |
| Error handling | Typed exception hierarchy mapped from Binance error codes |
| Architecture | Clean 3-layer separation: CLI → Logic → API Client |
| Security | API keys in `.env` (never hardcoded, never logged) |
| Retries | Exponential backoff on 502/503/504 gateway errors |

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py
│   ├── client.py          # Binance REST client (HMAC signing, retries)
│   ├── orders.py          # Order placement logic
│   ├── validators.py      # Input validation (all in one place)
│   ├── models.py          # Typed dataclasses for requests/responses
│   ├── exceptions.py      # Custom exception hierarchy
│   ├── config.py          # Environment-based configuration
│   └── logging_config.py  # JSON file logger + rich console handler
├── cli.py                 # CLI entry point (argparse + rich)
├── logs/
│   ├── trading_bot.log
├── .env.example           # Template for API credentials
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Prerequisites

- Python 3.10 or higher
- A [Binance Futures Testnet](https://demo-fapi.binance.com) account

### 2. Clone and install

```bash
git clone https://github.com/<your-username>/trading-bot.git
cd trading-bot

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your testnet credentials:

```
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

> **Note**: These are testnet-only credentials. Never use mainnet keys here.

---

## Running the Bot

### Interactive mode (recommended for first use)

```bash
python cli.py --interactive
```

Guides you through symbol → side → type → quantity → price with live validation and a confirmation prompt.

---

### Direct command mode

#### Market order — buy 0.001 BTC immediately at market price

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

#### Limit order — sell 0.05 ETH at $2250 (rests on the book)

```bash
python cli.py --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.05 --price 2250
```

#### Limit buy with custom time-in-force (IOC — fill immediately or cancel)

```bash
python cli.py --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.001 --price 42000 --tif IOC
```

---

### CLI flags reference

| Flag | Description | Default |
|---|---|---|
| `--symbol` | Trading pair, e.g. `BTCUSDT` | required |
| `--side` | `BUY` or `SELL` | required |
| `--type` | `MARKET`, `LIMIT`| required |
| `--quantity` | Order quantity | required |
| `--price` | Limit price (required for `LIMIT` orders) | 
| `--tif` | Time-in-force: `GTC` / `IOC` / `FOK` / `GTX` | `GTC` |
| `--reduce-only` | Mark as reduce-only (position closing) | false |
| `--interactive` / `-i` | Launch guided interactive mode | false |
| `--log-level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `--quiet` / `-q` | Suppress console output | false |

---

## Logging

Every run appends to `logs/trading_bot.log` in structured JSON format:

```json
{
  "timestamp": "2024-01-15T09:23:41.123456+00:00",
  "level": "INFO",
  "logger": "bot.orders",
  "message": "Order placed successfully",
  "order_id": 3212560892,
  "symbol": "BTCUSDT",
  "side": "BUY",
  "type": "MARKET",
  "status": "FILLED",
  "executed_qty": "0.001",
  "avg_price": "42318.50"
}
```

JSON logs are grep- and `jq`-friendly:

```bash
# Show only errors
jq 'select(.level == "ERROR")' logs/trading_bot.log

# Show all order placements
jq 'select(.message == "Order placed successfully")' logs/trading_bot.log
```

logs from a live testnet session are in `logs/trading_bot.log` 

---

## Error Handling

The bot uses a typed exception hierarchy rather than bare `except Exception`:

```
TradingBotError
├── ValidationError          # bad user input
├── ConfigurationError       # missing API keys
├── NetworkError             # timeout / connection failure
└── APIError                 # Binance API error
    ├── AuthenticationError  # invalid key / signature
    ├── InsufficientFundsError
    ├── InvalidSymbolError
    ├── InvalidOrderError
    └── RateLimitError
```

Binance error codes are mapped automatically (e.g. code `-2018` → `InsufficientFundsError`).

---

## Architecture Notes

The codebase follows a strict 3-layer separation:

```
cli.py  →  bot/orders.py  →  bot/client.py  →  Binance API
 (UI)        (logic)           (transport)
```

- `cli.py` handles argument parsing, display, and user interaction only.  
- `orders.py` knows about trading concepts (order types, symbols) but not HTTP.  
- `client.py` knows about HTTP and HMAC signing but not trading concepts.  
- Validators, models, exceptions, logging, and config are shared utilities.

This means you can swap the CLI for a web UI, or swap `requests` for `httpx`, without touching any business logic.

---

## Assumptions

- Testnet is used by default. Pass `--mainnet` to target mainnet (real funds — use with extreme caution).
- Quantity precision is validated to 3 decimal places. Some pairs may have stricter exchange-level filters (the API will return a clear error if so).
- The bot does not manage positions or account state — it is purely an order execution tool.

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP client for Binance REST API |
| `python-dotenv` | Loads `.env` file into environment |
| `rich` | Coloured terminal output, tables, prompts |