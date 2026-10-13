"""Invoice aging report from a CSV export. Standard library only."""
import csv
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")

def summarize(path: str, as_of: date) -> dict:
    totals = {name: Decimal("0.00") for name in BUCKETS}
    seen = set()
    count = 0
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"invoice_id", "due_date", "amount"}.issubset(reader.fieldnames):
            raise ValueError("required columns: invoice_id,due_date,amount")
        for line, row in enumerate(reader, 2):
            try:
                invoice_id = row["invoice_id"].strip()
                due = date.fromisoformat(row["due_date"].strip())
                amount = Decimal(row["amount"].strip())
                if not invoice_id or invoice_id in seen or not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
                    raise ValueError("invalid invoice ID or amount")
            except (KeyError, AttributeError, InvalidOperation, ValueError) as exc:
                raise ValueError(f"line {line}: invalid invoice") from exc
            seen.add(invoice_id)
            days = (as_of - due).days
            bucket = ("current" if days <= 0 else "1-30" if days <= 30
                      else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+")
            totals[bucket] += amount
            count += 1
    return {"as_of": as_of.isoformat(), "invoices": count,
            "buckets": {key: str(value) for key, value in totals.items()},
            "total": str(sum(totals.values()))}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python aging.py invoices.csv YYYY-MM-DD")
    print(json.dumps(summarize(sys.argv[1], date.fromisoformat(sys.argv[2])), indent=2))
