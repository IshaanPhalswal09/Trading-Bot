"""
Input validation for order parameters.

All validators raise ValueError with a clear message on failure.
They return the cleaned/normalised value on success.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}


def validate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s or not s.isalpha():
        raise ValueError(
            f"Invalid symbol '{symbol}'. Must be alphabetic, e.g. BTCUSDT."
        )
    return s


def validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    return s


def validate_order_type(order_type: str) -> str:
    t = order_type.strip().upper()
    if t not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    return t


def validate_quantity(quantity: str | float) -> Decimal:
    try:
        q = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Invalid quantity '{quantity}'. Must be a positive number.")
    if q <= 0:
        raise ValueError(f"Quantity must be > 0, got {quantity}.")
    return q


def validate_price(price: str | float | None, order_type: str) -> Decimal | None:
    if order_type in ("LIMIT", "STOP_MARKET") and price is None:
        raise ValueError(f"Price is required for {order_type} orders.")
    if price is None:
        return None
    try:
        p = Decimal(str(price))
    except InvalidOperation:
        raise ValueError(f"Invalid price '{price}'. Must be a positive number.")
    if p <= 0:
        raise ValueError(f"Price must be > 0, got {price}.")
    return p


def validate_stop_price(stop_price: str | float | None, order_type: str) -> Decimal | None:
    if order_type == "STOP_MARKET" and stop_price is None:
        raise ValueError("stopPrice is required for STOP_MARKET orders.")
    if stop_price is None:
        return None
    try:
        sp = Decimal(str(stop_price))
    except InvalidOperation:
        raise ValueError(f"Invalid stop price '{stop_price}'. Must be a positive number.")
    if sp <= 0:
        raise ValueError(f"Stop price must be > 0, got {stop_price}.")
    return sp


def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float,
    price: str | float | None = None,
    stop_price: str | float | None = None,
) -> dict:
    """
    Validate all order fields at once. Returns a clean dict ready for the API.
    Raises ValueError with the first problem found.
    """
    clean_type = validate_order_type(order_type)
    clean_price = validate_price(price, clean_type)
    clean_stop = validate_stop_price(stop_price, clean_type)

    return {
        "symbol": validate_symbol(symbol),
        "side": validate_side(side),
        "type": clean_type,
        "quantity": validate_quantity(quantity),
        "price": clean_price,
        "stopPrice": clean_stop,
    }
