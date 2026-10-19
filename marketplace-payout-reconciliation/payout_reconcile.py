"""Offline reconciliation of fictional marketplace orders and payout statements.

Money uses Decimal; every unique order identifier is reported exactly once.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

CENT = Decimal("0.01")
CURRENCY_RE = re.compile(r"[A-Z]{3}\Z")
REPORT_COLUMNS = [
    "order_id", "currency", "payout_currency", "gross", "refund", "fee",
    "expected_net", "paid_net", "difference", "status",
]


def money(text: str, *, signed: bool = False) -> Decimal:
    try:
        number = Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Invalid monetary value {text!r}") from None
    if not number.is_finite():
        raise ValueError(f"Expected finite cents, got {text!r}")
    try:
        rounded = number.quantize(CENT)
    except InvalidOperation:
        raise ValueError(f"Monetary value is out of range: {text!r}") from None
    if number != rounded:
        raise ValueError(f"Expected finite cents, got {text!r}")
    if not signed and number < 0:
        raise ValueError(f"Negative amount not permitted: {text!r}")
    return number.quantize(CENT)


def read_records(path: Path, *, kind: str) -> dict[str, dict]:
    required = (
        ("order_id", "currency", "gross", "refund", "fee")
        if kind == "orders" else
        ("order_id", "currency", "net_paid")
    )
    rows: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{kind}: required CSV columns: {','.join(required)}")
        for line_number, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f"{kind} line {line_number}: extra CSV field")
            order_id = (row["order_id"] or "").strip()
            currency = (row["currency"] or "").strip()
            if not order_id or not CURRENCY_RE.fullmatch(currency):
                raise ValueError(
                    f"{kind} line {line_number}: invalid order ID or currency")
            if order_id in rows:
                raise ValueError(
                    f"{kind} line {line_number}: repeated order ID {order_id!r}")
            record = {"order_id": order_id, "currency": currency}
            if kind == "orders":
                record.update({
                    field: money(row[field] or "")
                    for field in ("gross", "refund", "fee")
                })
                if record["refund"] > record["gross"]:
                    raise ValueError(
                        f"{kind} line {line_number}: refund exceeds gross amount")
            else:
                record["net_paid"] = money(row["net_paid"] or "", signed=True)
            rows[order_id] = record
    return rows


def reconcile(orders: dict[str, dict], payouts: dict[str, dict],
              tolerance: Decimal = Decimal("0.00")
              ) -> tuple[list[dict[str, str]], dict[str, int]]:
    if not tolerance.is_finite() or tolerance < 0 or tolerance != tolerance.quantize(CENT):
        raise ValueError("Tolerance must be nonnegative, in cents")
    rows = []
    counts: Counter[str] = Counter()
    for order_id in sorted(orders.keys() | payouts.keys()):
        order = orders.get(order_id)
        payout = payouts.get(order_id)
        currency = (order or payout)["currency"]
        gross = order["gross"] if order else None
        refund = order["refund"] if order else None
        fee = order["fee"] if order else None
        expected = (gross - refund - fee) if order else None
        paid = payout["net_paid"] if payout else None
        difference = None
        if order is None:
            status = "orphan_payout"
        elif payout is None:
            status = "missing_payout"
        elif currency != payout["currency"]:
            status = "currency_mismatch"
        else:
            difference = paid - expected
            status = "matched" if abs(difference) <= tolerance else "amount_mismatch"
        counts[status] += 1
        rows.append({
            "order_id": order_id, "currency": currency,
            "payout_currency": payout["currency"] if payout else "",
            "gross": format_decimal(gross),
            "refund": format_decimal(refund),
            "fee": format_decimal(fee),
            "expected_net": format_decimal(expected),
            "paid_net": format_decimal(paid),
            "difference": format_decimal(difference),
            "status": status,
        })
    result = {"total": len(rows), **{
        key: counts[key] for key in
        ("matched", "amount_mismatch", "missing_payout",
         "orphan_payout", "currency_mismatch")
    }}
    return rows, result


def format_decimal(value: Decimal | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def safe_cell(text: str) -> str:
    """Prevent spreadsheet interpretation of formula-like free-text cells."""
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def export(rows: list[dict[str, str]], summary: dict[str, int],
           output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "reconciliation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: safe_cell(row[key]) if key == "order_id"
                             else row[key] for key in REPORT_COLUMNS})
    (output / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare order-derived net proceeds with marketplace payouts")
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--payouts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance", default="0.00",
                        help="Allowed absolute difference in currency units (default: 0)")
    args = parser.parse_args(argv)
    try:
        tolerance = money(args.tolerance)
        rows, summary = reconcile(
            read_records(args.orders, kind="orders"),
            read_records(args.payouts, kind="payouts"),
            tolerance,
        )
        export(rows, summary, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
