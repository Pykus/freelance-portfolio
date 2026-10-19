"""Audit changes in supplier unit costs and their impact on retail gross margins.

Offline only. All money uses Decimal; no external integrations or dependencies.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MAX_MONEY = Decimal("1000000000000")
COLUMNS = (
    "sku", "status", "old_currency", "new_currency", "old_unit_cost",
    "new_unit_cost", "retail_price", "cost_change_percent",
    "gross_margin_percent", "flags",
)


@dataclass(frozen=True)
class Product:
    sku: str
    currency: str
    unit_cost: Decimal
    retail_price: Decimal


def money(text: str, *, source: str, row: int, field: str) -> Decimal:
    try:
        value = Decimal(text.strip())
        if (not value.is_finite() or value < 0 or value > MAX_MONEY
                or value != value.quantize(CENT)):
            raise ValueError("amount must be nonnegative, finite, and have at most two decimals")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{source} row {row}: invalid {field}: {text!r}") from exc
    return value


def load_catalog(path: Path) -> dict[str, Product]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        needed = {"sku", "currency", "unit_cost", "retail_price"}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError(f"{path}: CSV needs sku,currency,unit_cost,retail_price")
        catalog: dict[str, Product] = {}
        for number, record in enumerate(reader, 2):
            sku = (record["sku"] or "").strip()
            currency = (record["currency"] or "").strip()
            if not sku or len(sku) > 100:
                raise ValueError(f"{path} row {number}: SKU missing or too long")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError(f"{path} row {number}: currency must be an uppercase 3-letter code")
            if sku in catalog:
                raise ValueError(f"{path} row {number}: repeated SKU {sku!r}")
            cost = money(record["unit_cost"] or "", source=str(path),
                         row=number, field="unit_cost")
            price = money(record["retail_price"] or "", source=str(path),
                          row=number, field="retail_price")
            catalog[sku] = Product(sku, currency, cost, price)
    return catalog


def fmt(value: Decimal | None) -> str:
    return "" if value is None else f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"


def audit(
    previous: dict[str, Product], current: dict[str, Product],
    *, max_cost_increase: Decimal = Decimal("10"),
    min_margin: Decimal = Decimal("20"),
) -> tuple[list[dict[str, str]], dict[str, int]]:
    if (not max_cost_increase.is_finite() or max_cost_increase < 0
            or not min_margin.is_finite() or not Decimal("0") <= min_margin <= HUNDRED):
        raise ValueError("Cost threshold must be nonnegative; margin target must be in [0, 100]")
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for sku in sorted(previous.keys() | current.keys()):
        old = previous.get(sku)
        new = current.get(sku)
        status = ("added" if old is None else "removed" if new is None else
                  "unchanged" if old == new else "changed")
        flags: list[str] = []
        growth: Decimal | None = None
        margin: Decimal | None = None
        if new is not None:
            if new.retail_price == 0:
                flags.append("zero_retail_price")
            else:
                margin = (new.retail_price - new.unit_cost) * HUNDRED / new.retail_price
                if new.unit_cost > new.retail_price:
                    flags.append("price_below_cost")
                if margin < min_margin:
                    flags.append("margin_below_target")
            if old is not None:
                if old.currency != new.currency:
                    flags.append("currency_changed")
                elif old.unit_cost == 0:
                    if new.unit_cost > 0:
                        flags.append("cost_from_zero")
                else:
                    growth = (new.unit_cost - old.unit_cost) * HUNDRED / old.unit_cost
                    if growth > max_cost_increase:
                        flags.append("cost_increase_over_limit")
        counts[status] += 1
        for flag in flags:
            counts["flag_" + flag] += 1
        rows.append({
            "sku": sku, "status": status,
            "old_currency": old.currency if old else "",
            "new_currency": new.currency if new else "",
            "old_unit_cost": fmt(old.unit_cost if old else None),
            "new_unit_cost": fmt(new.unit_cost if new else None),
            "retail_price": fmt(new.retail_price if new else None),
            "cost_change_percent": fmt(growth),
            "gross_margin_percent": fmt(margin),
            "flags": " | ".join(flags),
        })
    result = {
        key: counts[key] for key in
        ("added", "removed", "changed", "unchanged",
         "flag_cost_increase_over_limit", "flag_margin_below_target",
         "flag_price_below_cost", "flag_currency_changed",
         "flag_cost_from_zero", "flag_zero_retail_price")
    }
    result["total_skus"] = len(rows)
    return rows, result


def safe_excel_cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_report(rows: list[dict[str, str]], summary: dict[str, int],
                 output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "price_review.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({
            col: safe_excel_cell(row[col]) for col in COLUMNS
        } for row in rows)
    (output / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare offline supplier price lists and report margin risks")
    parser.add_argument("--previous", type=Path, default=ROOT / "examples/before.csv")
    parser.add_argument("--current", type=Path, default=ROOT / "examples/after.csv")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--max-cost-increase", default="10",
                        help="Percent, strictly greater than this threshold is flagged")
    parser.add_argument("--min-margin", default="20",
                        help="Minimum acceptable gross margin percentage")
    args = parser.parse_args(argv)
    try:
        threshold = Decimal(args.max_cost_increase)
        margin = Decimal(args.min_margin)
        records, summary = audit(
            load_catalog(args.previous), load_catalog(args.current),
            max_cost_increase=threshold, min_margin=margin)
        write_report(records, summary, args.output)
    except (InvalidOperation, ValueError, OSError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
