"""
Order placement logic.

Builds API parameters, calls the Binance client, and returns a
structured OrderResult with validated / normalised fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any

from .client import BinanceFuturesClient, BinanceAPIError
from .logging_config import get_logger
from .validators import validate_all

logger = get_logger(__name__)

ORDER_ENDPOINT = "/fapi/v1/order"


@dataclass
class OrderResult:
    """Normalised, schema-safe representation of a Binance order response."""

    order_id: int
    client_order_id: str
    symbol: str
    side: str
    type: str
    status: str
    orig_qty: str
    executed_qty: str
    avg_price: str
    price: str
    time_in_force: str
    raw: dict  # full API response preserved for debugging

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw")  # keep structured output clean; raw lives in logs
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_api_response(cls, data: dict) -> "OrderResult":
        """Parse raw Binance response into a typed OrderResult."""
        return cls(
            order_id=int(data["orderId"]),
            client_order_id=data.get("clientOrderId", ""),
            symbol=data["symbol"],
            side=data["side"],
            type=data["type"],
            status=data["status"],
            orig_qty=data.get("origQty", "0"),
            executed_qty=data.get("executedQty", "0"),
            avg_price=data.get("avgPrice", "0"),
            price=data.get("price", "0"),
            time_in_force=data.get("timeInForce", ""),
            raw=data,
        )


def _build_params(validated: dict) -> dict:
    """Convert validated input dict into Binance API parameter dict."""
    params: dict[str, Any] = {
        "symbol": validated["symbol"],
        "side": validated["side"],
        "type": validated["type"],
        "quantity": str(validated["quantity"]),
    }

    order_type = validated["type"]

    if order_type == "LIMIT":
        params["price"] = str(validated["price"])
        params["timeInForce"] = "GTC"

    elif order_type == "STOP_MARKET":
        params["stopPrice"] = str(validated["stopPrice"])

    return params


def place_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: str | float | None = None,
    stop_price: str | float | None = None,
) -> OrderResult:
    """
    Validate inputs, place an order, and return a structured OrderResult.

    Raises:
        ValueError  – invalid parameters
        BinanceAPIError – Binance rejected the order
        NetworkError – connection / timeout failure
    """
    # --- Validate ---
    validated = validate_all(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
    )
    logger.info(
        "Placing order | symbol=%s side=%s type=%s qty=%s price=%s",
        validated["symbol"],
        validated["side"],
        validated["type"],
        validated["quantity"],
        validated.get("price"),
    )

    # --- Build params ---
    params = _build_params(validated)
    logger.debug("Order params: %s", params)

    # --- Guardrail: sanity-check before sending ---
    _guardrails(validated)

    # --- Send to exchange ---
    response = client.post(ORDER_ENDPOINT, params=params)
    logger.info("Order response: %s", json.dumps(response, indent=2))

    result = OrderResult.from_api_response(response)
    logger.info(
        "Order accepted | orderId=%s status=%s executedQty=%s avgPrice=%s",
        result.order_id,
        result.status,
        result.executed_qty,
        result.avg_price,
    )
    return result


# ---------------------------------------------------------------------------
# Guardrails – lightweight pre-flight checks
# ---------------------------------------------------------------------------

MAX_QUANTITY = Decimal("1000")   # sanity cap for testnet
MIN_NOTIONAL = Decimal("5")      # USDT-equivalent minimum


def _guardrails(validated: dict) -> None:
    """
    Block obviously unsafe or invalid orders before they hit the wire.
    Raises ValueError with a clear message.
    """
    qty: Decimal = validated["quantity"]
    price: Decimal | None = validated.get("price")

    if qty > MAX_QUANTITY:
        raise ValueError(
            f"Quantity {qty} exceeds safety cap of {MAX_QUANTITY}. "
            "Increase MAX_QUANTITY in orders.py if intentional."
        )

    if price is not None and price * qty < MIN_NOTIONAL:
        raise ValueError(
            f"Notional value {price * qty:.4f} USDT is below minimum {MIN_NOTIONAL} USDT."
        )
