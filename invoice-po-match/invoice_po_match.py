"""Deterministic two-way invoice-to-purchase-order checks using integer cents."""
import argparse
import csv
import json
import re
from pathlib import Path

MONEY = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")
FIELDS = ("invoice_id", "po_id", "status", "issues", "computed_subtotal",
          "claimed_subtotal", "tax", "claimed_total")


class DataError(ValueError):
    """Invalid input."""


def required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{name} must be a nonempty string")
    return value.strip()


def money_to_cents(value, name):
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        raise DataError(f"{name} must be a nonnegative decimal string (max 2 places)")
    whole, _, fraction = value.partition(".")
    return int(whole) * 100 + int((fraction + "00")[:2])


def fmt(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def parse_items(items, label):
    if not isinstance(items, list) or not items:
        raise DataError(f"{label} must be a nonempty list")
    result = {}
    for number, item in enumerate(items, 1):
        key = f"{label}[{number}]"
        if not isinstance(item, dict):
            raise DataError(f"{key} must be an object")
        sku = required_text(item.get("sku"), f"{key}.sku")
        qty = item.get("quantity")
        if type(qty) is not int or qty <= 0:
            raise DataError(f"{key}.quantity must be a positive integer")
        price = money_to_cents(item.get("unit_price"), f"{key}.unit_price")
        if sku in result:
            raise DataError(f"duplicate SKU {sku} in {label}")
        result[sku] = (qty, price)
    return result


def load_json_list(path):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            rows = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f"cannot load {Path(path).name}: {exc}") from exc
    if not isinstance(rows, list):
        raise DataError("top-level document must be a JSON list")
    return rows


def parse_orders(rows):
    orders = {}
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise DataError(f"purchase order {number} must be an object")
        order_id = required_text(row.get("po_id"), "po_id")
        if order_id in orders:
            raise DataError(f"duplicate purchase order ID: {order_id}")
        currency = required_text(row.get("currency"), "currency")
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise DataError("currency must be a three-letter uppercase code")
        orders[order_id] = {
            "supplier": required_text(row.get("supplier"), "supplier"),
            "currency": currency,
            "items": parse_items(row.get("items"), f"purchase order {order_id}.items"),
        }
    return orders


def audit(rows, orders):
    reports = []
    seen = set()
    for number, row in enumerate(rows, 1):
        invoice_id, po_id = f"row-{number}", ""
        try:
            if not isinstance(row, dict):
                raise DataError("invoice must be an object")
            invoice_id = required_text(row.get("invoice_id"), "invoice_id")
            po_id = required_text(row.get("po_id"), "po_id")
            supplier = required_text(row.get("supplier"), "supplier")
            currency = required_text(row.get("currency"), "currency")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise DataError("currency must be a three-letter uppercase code")
            items = parse_items(row.get("items"), "invoice.items")
            subtotal = money_to_cents(row.get("claimed_subtotal"), "claimed_subtotal")
            tax = money_to_cents(row.get("tax"), "tax")
            total = money_to_cents(row.get("claimed_total"), "claimed_total")
            computed = sum(qty * price for qty, price in items.values())
        except DataError:
            reports.append(dict(invoice_id=invoice_id, po_id=po_id, status="REVIEW",
                                issues=["INVALID_RECORD"], computed_subtotal="",
                                claimed_subtotal="", tax="", claimed_total=""))
            continue

        issues = set()
        if invoice_id in seen:
            issues.add("DUPLICATE_INVOICE")
        seen.add(invoice_id)
        order = orders.get(po_id)
        if order is None:
            issues.add("PO_NOT_FOUND")
        else:
            if supplier != order["supplier"]:
                issues.add("SUPPLIER_MISMATCH")
            if currency != order["currency"]:
                issues.add("CURRENCY_MISMATCH")
            for sku, (qty, price) in items.items():
                expected = order["items"].get(sku)
                if expected is None:
                    issues.add("UNKNOWN_SKU")
                else:
                    if qty > expected[0]:
                        issues.add("QUANTITY_EXCEEDS_ORDER")
                    if price != expected[1]:
                        issues.add("UNIT_PRICE_MISMATCH")
        if subtotal != computed:
            issues.add("SUBTOTAL_MISMATCH")
        if subtotal + tax != total:
            issues.add("TOTAL_MISMATCH")
        reports.append(dict(invoice_id=invoice_id, po_id=po_id,
                            status="REVIEW" if issues else "READY",
                            issues=sorted(issues), computed_subtotal=fmt(computed),
                            claimed_subtotal=fmt(subtotal), tax=fmt(tax),
                            claimed_total=fmt(total)))
    return reports


def save(reports, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(reports),
        "ready": sum(row["status"] == "READY" for row in reports),
        "review": sum(row["status"] == "REVIEW" for row in reports),
    }
    with (output / "invoice_report.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in reports:
            writer.writerow({**row, "issues": ";".join(row["issues"])})
    with (output / "invoice_report.json").open("w", encoding="utf-8") as file:
        json.dump({"summary": summary, "invoices": reports}, file, indent=2)
        file.write("\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit sample supplier invoices against purchase orders")
    parser.add_argument("--orders", required=True)
    parser.add_argument("--invoices", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        summary = save(audit(load_json_list(args.invoices),
                             parse_orders(load_json_list(args.orders))), args.output_dir)
    except (DataError, OSError) as exc:
        parser.exit(2, f"Input/output error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
