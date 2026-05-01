# 🤖 Binance Futures Testnet – Trading Bot

A clean, production-structured Python trading bot for Binance USDT-M Futures Testnet.  
Supports **Market**, **Limit**, and **Stop-Market** orders via a polished CLI with full logging, validation, and a test harness.

---

## Features

| Feature | Detail |
|---|---|
| **Order Types** | MARKET · LIMIT · STOP\_MARKET (bonus) |
| **Sides** | BUY · SELL |
| **CLI Modes** | Direct flags *and* interactive guided builder |
| **Validation** | Symbol, side, type, quantity, price, notional floor, quantity cap |
| **Guardrails** | Blocks sub-notional and oversized orders before hitting the wire |
| **Logging** | DEBUG to rotating file · WARNING to console (configurable) |
| **Retries** | Up to 3 attempts with exponential back-off on network failures |
| **Test Harness** | 10 unit/integration scenarios with pass/fail summary |
| **No heavy deps** | Only `httpx` + `python-dotenv` |

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # public API surface
│   ├── client.py            # Binance REST client (auth, retries, timeouts)
│   ├── orders.py            # order placement logic + OrderResult schema
│   ├── validators.py        # input validation (raises ValueError on bad input)
│   └── logging_config.py   # rotating file + console handlers
├── cli.py                   # CLI entry point (argparse + interactive mode)
├── test_harness.py          # 10-scenario test suite
├── logs/
│   ├── market_order.log     # sample MARKET order log
│   └── limit_order.log      # sample LIMIT order log
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

### 1 · Get Testnet Credentials

1. Go to [https://testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Log in (GitHub OAuth) → **API Key** tab → generate a key pair
3. Copy your **API Key** and **Secret**

### 2 · Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3 · Configure Credentials

```bash
cp .env.example .env
# Edit .env and fill in BINANCE_API_KEY and BINANCE_API_SECRET
```

Or export them directly:

```bash
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
```

---

## Usage

### Direct flags (scriptable)

```bash
# Market BUY – 0.001 BTC
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

# Limit SELL – 0.1 ETH at $3,200
python cli.py --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.1 --price 3200

# Stop-Market SELL – trigger if BTC drops to $60,000  [BONUS]
python cli.py --symbol BTCUSDT --side SELL --type STOP_MARKET --quantity 0.001 --stop-price 60000

# JSON-only output (for piping / scripting)
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001 --json-only

# Verbose (DEBUG logs to console)
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001 --verbose
```

### Interactive mode (guided UX) [BONUS]

```bash
python cli.py --interactive
# or
python cli.py -i
```

The bot will walk you through each field with inline validation and a confirmation prompt before sending.

---

## Example Output

```
╔══════════════════════════════════════════════════════╗
║        Binance Futures Testnet  ·  Trading Bot       ║
║                  USDT-M Perpetuals                   ║
╚══════════════════════════════════════════════════════╝
──────────────────────────────────────────────────────
  Order Request Summary
──────────────────────────────────────────────────────
  Symbol:              BTCUSDT
  Side:                BUY
  Type:                MARKET
  Quantity:            0.001
──────────────────────────────────────────────────────

  Confirm order? [y/N]: y

──────────────────────────────────────────────────────
  ✓ Order Accepted
──────────────────────────────────────────────────────
  Order ID:            4011265842
  Client OID:          x-Testnet-abc123
  Symbol:              BTCUSDT
  Side:                BUY
  Type:                MARKET
  Status:              FILLED
  Orig Qty:            0.001
  Executed Qty:        0.001
  Avg Price:           64872.50
  Limit Price:         —
  Time In Force:       —
──────────────────────────────────────────────────────

  ✓ Order placed successfully!
```

---

## Running the Test Harness

```bash
python test_harness.py
```

Expected output:
```
──────────────────────────────────────────────────────
  Trading Bot · Test Harness  (10 scenarios)
──────────────────────────────────────────────────────

  ✓ test_valid_symbol
  ✓ test_numeric_symbol
  ✓ test_empty_symbol
  ✓ test_valid_sides
  ✓ test_invalid_side
  ✓ test_positive_quantity
  ✓ test_zero_quantity_rejected
  ✓ test_limit_without_price_raises
  ✓ test_market_order_success
  ✓ test_api_error_raised

  10/10 passed
──────────────────────────────────────────────────────
```

---

## Logging

All API calls are logged to `logs/trading_bot.log` at DEBUG level.  
Console output is WARNING+ by default (use `--verbose` for DEBUG on console).

Log format:
```
2026-05-01T10:14:22 | DEBUG | bot.client | → POST /fapi/v1/order | attempt=1 | params={...}
2026-05-01T10:14:23 | INFO  | bot.orders | Order accepted | orderId=... status=FILLED
```

---

## Assumptions & Design Decisions

- **No `python-binance` library** – uses `httpx` directly for full transparency and control over retries/timeouts.
- **`timeInForce=GTC`** is applied automatically to all LIMIT orders (standard convention).
- **Guardrails**: orders with quantity > 1000 or notional < 5 USDT are blocked client-side before being sent to the exchange.
- **Credentials** are read from environment variables (or `.env`); never hardcoded.
- **Rotating logs** cap at 5 MB × 3 backups to avoid disk bloat during extended testing.

---

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Validation error |
| 3 | Binance API error |
| 4 | Network failure |
| 5 | Unexpected error |
| 130 | Keyboard interrupt |
