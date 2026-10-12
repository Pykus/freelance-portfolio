"""Input validation for fictional order records."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

ORDER_ID = re.compile(r"O-[0-9]{3,8}\Z")


class DataError(Exception):
    """Malformed input or invalid order data."""


def read_orders(path):
    try:
        with open(path, encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise DataError(f"Cannot read orders JSON: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"orders"} or not isinstance(doc["orders"], list):
        raise DataError("Input must be a JSON object with one 'orders' array")
    return doc["orders"]


def normalize(raw):
    if not isinstance(raw, dict) or set(raw) != {"order_id", "customer", "amount_usd", "status", "order_date"}:
        raise DataError("expected exactly order_id, customer, amount_usd, status, order_date")
    oid = raw["order_id"]
    if not isinstance(oid, str) or not ORDER_ID.fullmatch(oid):
        raise DataError("invalid order_id")
    customer = raw["customer"]
    if not isinstance(customer, str) or not customer.strip() or len(customer.strip()) > 100:
        raise DataError("invalid customer")
    amount = raw["amount_usd"]
    if not isinstance(amount, str):
        raise DataError("amount_usd must be a decimal string")
    try:
        amount_decimal = Decimal(amount)
    except InvalidOperation as exc:
        raise DataError("invalid amount_usd") from exc
    if not amount_decimal.is_finite() or amount_decimal <= 0 or amount_decimal > 1_000_000:
        raise DataError("amount_usd must be greater than zero and at most 1000000")
    if amount_decimal.as_tuple().exponent < -2:
        raise DataError("amount_usd must have at most two decimal places")
    cents = int(amount_decimal * 100)
    if raw["status"] not in ("paid", "pending"):
        raise DataError("status must be paid or pending")
    try:
        if not isinstance(raw["order_date"], str) or date.fromisoformat(raw["order_date"]).isoformat() != raw["order_date"]:
            raise ValueError("noncanonical date")
    except ValueError as exc:
        raise DataError("order_date must be an ISO YYYY-MM-DD date") from exc
    return (oid, customer.strip(), cents, raw["status"], raw["order_date"])


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"
