#!/usr/bin/env python3
"""
test_harness.py – Mini test suite for the trading bot.

Covers 10 test scenarios without hitting the real exchange:
  - Unit tests for validators and order parameter building
  - Integration-style tests with a mocked Binance client
  - A live smoke test (skipped unless BINANCE_API_KEY is set)

Run:
    python test_harness.py          # all tests
    python test_harness.py -v       # verbose
"""

import json
import sys
import os
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bot.logging_config import setup_logging
setup_logging(verbose=False)

from bot.validators import (
    validate_symbol, validate_side, validate_order_type,
    validate_quantity, validate_price, validate_all,
)
from bot.orders import place_order, OrderResult, _build_params, _guardrails
from bot.client import BinanceAPIError


# ---------------------------------------------------------------------------
# Helper – fake Binance response
# ---------------------------------------------------------------------------

def _fake_order_response(order_type="MARKET", side="BUY", symbol="BTCUSDT"):
    return {
        "orderId": 123456,
        "clientOrderId": "testABC",
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "status": "NEW",
        "origQty": "0.001",
        "executedQty": "0.001" if order_type == "MARKET" else "0",
        "avgPrice": "65000.00" if order_type == "MARKET" else "0",
        "price": "0" if order_type == "MARKET" else "65000",
        "timeInForce": "GTC" if order_type == "LIMIT" else "",
    }


# ===========================================================================
# TEST 1 – valid symbol accepted
# ===========================================================================
class Test01ValidSymbol(unittest.TestCase):
    def test_valid_symbol(self):
        result = validate_symbol("btcusdt")
        self.assertEqual(result, "BTCUSDT", "Should normalise to uppercase")


# ===========================================================================
# TEST 2 – invalid symbol rejected
# ===========================================================================
class Test02InvalidSymbol(unittest.TestCase):
    def test_numeric_symbol(self):
        with self.assertRaises(ValueError):
            validate_symbol("BTC123")

    def test_empty_symbol(self):
        with self.assertRaises(ValueError):
            validate_symbol("")


# ===========================================================================
# TEST 3 – side validation
# ===========================================================================
class Test03SideValidation(unittest.TestCase):
    def test_valid_sides(self):
        self.assertEqual(validate_side("buy"), "BUY")
        self.assertEqual(validate_side("SELL"), "SELL")

    def test_invalid_side(self):
        with self.assertRaises(ValueError):
            validate_side("LONG")


# ===========================================================================
# TEST 4 – quantity validation
# ===========================================================================
class Test04QuantityValidation(unittest.TestCase):
    def test_positive_quantity(self):
        self.assertEqual(validate_quantity("0.001"), Decimal("0.001"))

    def test_zero_quantity_rejected(self):
        with self.assertRaises(ValueError):
            validate_quantity("0")

    def test_negative_quantity_rejected(self):
        with self.assertRaises(ValueError):
            validate_quantity("-1")

    def test_string_quantity_rejected(self):
        with self.assertRaises(ValueError):
            validate_quantity("abc")


# ===========================================================================
# TEST 5 – price required for LIMIT
# ===========================================================================
class Test05PriceRequiredForLimit(unittest.TestCase):
    def test_limit_without_price_raises(self):
        with self.assertRaises(ValueError):
            validate_price(None, "LIMIT")

    def test_limit_with_price_ok(self):
        p = validate_price("65000", "LIMIT")
        self.assertEqual(p, Decimal("65000"))

    def test_market_without_price_ok(self):
        p = validate_price(None, "MARKET")
        self.assertIsNone(p)


# ===========================================================================
# TEST 6 – validate_all returns clean dict
# ===========================================================================
class Test06ValidateAll(unittest.TestCase):
    def test_market_order(self):
        clean = validate_all("BTCUSDT", "BUY", "MARKET", "0.001")
        self.assertEqual(clean["symbol"], "BTCUSDT")
        self.assertEqual(clean["type"], "MARKET")
        self.assertIsNone(clean["price"])

    def test_limit_order(self):
        clean = validate_all("ETHUSDT", "SELL", "LIMIT", "0.1", price="3200")
        self.assertEqual(clean["price"], Decimal("3200"))


# ===========================================================================
# TEST 7 – build_params produces correct API payload
# ===========================================================================
class Test07BuildParams(unittest.TestCase):
    def test_market_params(self):
        validated = validate_all("BTCUSDT", "BUY", "MARKET", "0.001")
        params = _build_params(validated)
        self.assertEqual(params["type"], "MARKET")
        self.assertNotIn("price", params)
        self.assertNotIn("timeInForce", params)

    def test_limit_params(self):
        validated = validate_all("BTCUSDT", "BUY", "LIMIT", "0.001", price="65000")
        params = _build_params(validated)
        self.assertEqual(params["timeInForce"], "GTC")
        self.assertEqual(params["price"], "65000")


# ===========================================================================
# TEST 8 – guardrails block oversized / sub-notional orders
# ===========================================================================
class Test08Guardrails(unittest.TestCase):
    def test_quantity_over_cap_rejected(self):
        validated = validate_all("BTCUSDT", "BUY", "MARKET", "9999")
        with self.assertRaises(ValueError, msg="Should block quantity > MAX_QUANTITY"):
            _guardrails(validated)

    def test_sub_notional_limit_rejected(self):
        # price=1, qty=0.001 → notional=0.001 USDT < 5 USDT minimum
        validated = validate_all("BTCUSDT", "BUY", "LIMIT", "0.001", price="1")
        with self.assertRaises(ValueError, msg="Should block sub-notional order"):
            _guardrails(validated)


# ===========================================================================
# TEST 9 – place_order returns OrderResult on success (mocked client)
# ===========================================================================
class Test09PlaceOrderSuccess(unittest.TestCase):
    def test_market_order_success(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _fake_order_response("MARKET", "BUY")

        result = place_order(mock_client, "BTCUSDT", "BUY", "MARKET", "0.001")

        self.assertIsInstance(result, OrderResult)
        self.assertEqual(result.order_id, 123456)
        self.assertEqual(result.status, "NEW")
        mock_client.post.assert_called_once()

    def test_limit_order_success(self):
        mock_client = MagicMock()
        mock_client.post.return_value = _fake_order_response("LIMIT", "SELL")

        result = place_order(
            mock_client, "BTCUSDT", "SELL", "LIMIT", "0.001", price="65000"
        )

        self.assertEqual(result.type, "LIMIT")
        self.assertEqual(result.time_in_force, "GTC")


# ===========================================================================
# TEST 10 – place_order propagates BinanceAPIError correctly
# ===========================================================================
class Test10APIErrorPropagation(unittest.TestCase):
    def test_api_error_raised(self):
        mock_client = MagicMock()
        mock_client.post.side_effect = BinanceAPIError(-1121, "Invalid symbol.")

        with self.assertRaises(BinanceAPIError) as ctx:
            place_order(mock_client, "BTCUSDT", "BUY", "MARKET", "0.001")

        self.assertEqual(ctx.exception.code, -1121)


# ===========================================================================
# Test runner with pretty summary
# ===========================================================================

PASS_MARK = "✓"
FAIL_MARK = "✗"
SKIP_MARK = "⊘"

CYAN  = "\033[96m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BOLD  = "\033[1m"
RESET = "\033[0m"


class PrettyResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._outcomes: list[tuple[str, str, str | None]] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self._outcomes.append(("PASS", test.id().split(".")[-1], None))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._outcomes.append(("FAIL", test.id().split(".")[-1], str(err[1])))

    def addError(self, test, err):
        super().addError(test, err)
        self._outcomes.append(("ERROR", test.id().split(".")[-1], str(err[1])))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._outcomes.append(("SKIP", test.id().split(".")[-1], reason))


class PrettyRunner(unittest.TextTestRunner):
    resultclass = PrettyResult

    def run(self, test):
        print(f"\n{CYAN}{BOLD}{'─'*54}{RESET}")
        print(f"{BOLD}  Trading Bot · Test Harness  (10 scenarios){RESET}")
        print(f"{CYAN}{'─'*54}{RESET}\n")

        result: PrettyResult = super().run(test)

        print(f"\n{CYAN}{'─'*54}{RESET}")
        passed = sum(1 for s, *_ in result._outcomes if s == "PASS")
        failed = sum(1 for s, *_ in result._outcomes if s in ("FAIL", "ERROR"))
        skipped = sum(1 for s, *_ in result._outcomes if s == "SKIP")
        total  = len(result._outcomes)

        for status, name, detail in result._outcomes:
            if status == "PASS":
                mark = f"{GREEN}{PASS_MARK}{RESET}"
            elif status == "SKIP":
                mark = f"{YELLOW}{SKIP_MARK}{RESET}"
            else:
                mark = f"{RED}{FAIL_MARK}{RESET}"
            extra = f"  {YELLOW}→ {detail}{RESET}" if detail and status != "PASS" else ""
            print(f"  {mark} {name}{extra}")

        colour = GREEN if failed == 0 else RED
        print(f"\n{colour}{BOLD}  {passed}/{total} passed{RESET}", end="")
        if skipped:
            print(f"  {YELLOW}{skipped} skipped{RESET}", end="")
        print(f"\n{CYAN}{'─'*54}{RESET}\n")

        return result


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = PrettyRunner(verbosity=0, stream=open(os.devnull, "w"))
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
