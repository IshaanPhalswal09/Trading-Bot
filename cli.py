#!/usr/bin/env python3
"""
cli.py – Command-line interface for the Binance Futures Testnet trading bot.

Supports two modes:
  1. Direct flags  (scriptable / CI-friendly)
  2. Interactive   (guided menus with validation feedback) [BONUS]

Usage examples
--------------
# Market BUY
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

# Limit SELL
python cli.py --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.1 --price 3200

# Stop-Market (bonus order type)
python cli.py --symbol BTCUSDT --side SELL --type STOP_MARKET --quantity 0.001 --stop-price 60000

# Interactive mode
python cli.py --interactive
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap – ensure project root on path & .env loaded
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass  # dotenv optional

from bot.logging_config import setup_logging, get_logger
from bot.client import BinanceFuturesClient, BinanceAPIError, NetworkError
from bot.orders import place_order
from bot.validators import VALID_SIDES, VALID_ORDER_TYPES

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# ANSI colour helpers (no third-party deps)
# ---------------------------------------------------------------------------
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

def _c(colour: str, text: str) -> str:
    return f"{colour}{text}{RESET}"

def banner():
    print(_c(CYAN, BOLD + """
╔══════════════════════════════════════════════════════╗
║        Binance Futures Testnet  ·  Trading Bot       ║
║                  USDT-M Perpetuals                   ║
╚══════════════════════════════════════════════════════╝""" + RESET))

def print_summary(symbol, side, order_type, quantity, price=None, stop_price=None):
    print(_c(DIM, "─" * 54))
    print(_c(BOLD, "  Order Request Summary"))
    print(_c(DIM, "─" * 54))
    rows = [
        ("Symbol",     symbol),
        ("Side",       _c(GREEN if side == "BUY" else RED, side)),
        ("Type",       order_type),
        ("Quantity",   str(quantity)),
    ]
    if price:
        rows.append(("Price", str(price)))
    if stop_price:
        rows.append(("Stop Price", str(stop_price)))
    for label, val in rows:
        print(f"  {_c(CYAN, label+':'): <20} {val}")
    print(_c(DIM, "─" * 54))

def print_result(result):
    print(_c(DIM, "─" * 54))
    print(_c(GREEN, BOLD + "  ✓ Order Accepted" + RESET))
    print(_c(DIM, "─" * 54))
    rows = [
        ("Order ID",      str(result.order_id)),
        ("Client OID",    result.client_order_id),
        ("Symbol",        result.symbol),
        ("Side",          _c(GREEN if result.side == "BUY" else RED, result.side)),
        ("Type",          result.type),
        ("Status",        _c(YELLOW, result.status)),
        ("Orig Qty",      result.orig_qty),
        ("Executed Qty",  result.executed_qty),
        ("Avg Price",     result.avg_price if result.avg_price != "0" else "—"),
        ("Limit Price",   result.price if result.price != "0" else "—"),
        ("Time In Force", result.time_in_force or "—"),
    ]
    for label, val in rows:
        print(f"  {_c(CYAN, label+':'): <22} {val}")
    print(_c(DIM, "─" * 54))

def print_error(msg: str):
    print(_c(RED, f"\n  ✗ Error: {msg}\n"))

# ---------------------------------------------------------------------------
# Interactive mode (BONUS enhanced UX)
# ---------------------------------------------------------------------------

def _prompt(prompt: str, default: str | None = None, validator=None) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        raw = input(f"  {_c(CYAN, '›')} {prompt}{hint}: ").strip()
        if not raw and default:
            raw = default
        if not raw:
            print(_c(YELLOW, "    This field is required."))
            continue
        if validator:
            try:
                validator(raw)
                return raw
            except ValueError as e:
                print(_c(YELLOW, f"    {e}"))
        else:
            return raw

def _choose(prompt: str, options: list[str]) -> str:
    print(f"\n  {_c(BOLD, prompt)}")
    for i, opt in enumerate(options, 1):
        print(f"    {_c(CYAN, str(i)+'.')} {opt}")
    while True:
        raw = input(f"  {_c(CYAN, '›')} Choice [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(_c(YELLOW, f"    Enter a number between 1 and {len(options)}."))

def interactive_mode() -> dict:
    """Guide the user step-by-step and return validated kwargs for place_order."""
    from bot.validators import validate_symbol, validate_quantity, validate_price, validate_stop_price

    print(_c(BOLD, "\n  Interactive Order Builder\n"))

    symbol     = _prompt("Symbol (e.g. BTCUSDT)", default="BTCUSDT",
                          validator=validate_symbol).upper()
    side       = _choose("Side", sorted(VALID_SIDES))
    order_type = _choose("Order Type", sorted(VALID_ORDER_TYPES))
    quantity   = _prompt("Quantity", validator=validate_quantity)
    price      = None
    stop_price = None

    if order_type in ("LIMIT",):
        price = _prompt("Limit Price (USDT)")

    if order_type == "STOP_MARKET":
        stop_price = _prompt("Stop Price (USDT)")

    return dict(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
    )

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trading_bot",
        description="Place orders on Binance Futures Testnet (USDT-M)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--symbol",     type=str, help="Trading pair, e.g. BTCUSDT")
    p.add_argument("--side",       type=str, choices=sorted(VALID_SIDES),
                   help="BUY or SELL")
    p.add_argument("--type",       dest="order_type", type=str,
                   choices=sorted(VALID_ORDER_TYPES),
                   help="Order type: MARKET, LIMIT, STOP_MARKET")
    p.add_argument("--quantity",   type=str, help="Order quantity (base asset)")
    p.add_argument("--price",      type=str, default=None,
                   help="Limit price in USDT (required for LIMIT orders)")
    p.add_argument("--stop-price", dest="stop_price", type=str, default=None,
                   help="Stop price in USDT (required for STOP_MARKET orders)")
    p.add_argument("--interactive", "-i", action="store_true",
                   help="Launch interactive guided order builder")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print DEBUG logs to console")
    p.add_argument("--json-only", action="store_true",
                   help="Print only the JSON result (useful for piping)")
    return p

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args   = parser.parse_args()

    setup_logging(verbose=args.verbose)

    banner()

    # --- Load credentials from environment ---
    api_key    = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        print_error(
            "API credentials not found.\n"
            "    Set BINANCE_API_KEY and BINANCE_API_SECRET in your environment\n"
            "    or create a .env file in the project root."
        )
        sys.exit(1)

    # --- Gather order parameters ---
    if args.interactive:
        order_kwargs = interactive_mode()
    else:
        required = ["symbol", "side", "order_type", "quantity"]
        missing  = [f"--{r.replace('_', '-')}" for r in required
                    if not getattr(args, r, None)]
        if missing:
            parser.error(
                f"Missing required arguments: {', '.join(missing)}.\n"
                "Use --interactive for guided input."
            )
        order_kwargs = dict(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
        )

    # --- Show summary ---
    if not args.json_only:
        print_summary(**order_kwargs)
        confirm = input(_c(CYAN, "\n  Confirm order? [y/N]: ")).strip().lower()
        if confirm not in ("y", "yes"):
            print(_c(YELLOW, "\n  Order cancelled.\n"))
            sys.exit(0)

    # --- Place order ---
    try:
        with BinanceFuturesClient(api_key, api_secret) as client:
            result = place_order(client, **order_kwargs)

        if args.json_only:
            print(result.to_json())
        else:
            print_result(result)
            print(_c(GREEN, "\n  ✓ Order placed successfully!\n"))

        logger.info("CLI completed successfully | orderId=%s", result.order_id)
        sys.exit(0)

    except ValueError as e:
        print_error(str(e))
        logger.error("Validation error: %s", e)
        sys.exit(2)

    except BinanceAPIError as e:
        print_error(f"Binance rejected the order — {e}")
        logger.error("BinanceAPIError: code=%s msg=%s", e.code, e.message)
        sys.exit(3)

    except NetworkError as e:
        print_error(f"Network failure — {e}")
        logger.error("NetworkError: %s", e)
        sys.exit(4)

    except KeyboardInterrupt:
        print(_c(YELLOW, "\n\n  Interrupted by user.\n"))
        sys.exit(130)

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        logger.exception("Unexpected error: %s", e)
        sys.exit(5)


if __name__ == "__main__":
    main()
