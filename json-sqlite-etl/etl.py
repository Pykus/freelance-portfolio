"""Load validated JSON orders to SQLite and generate a deterministic audit report."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from validation import DataError, read_orders, normalize, money

SCHEMA = """CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    status TEXT NOT NULL CHECK(status IN ('paid', 'pending')),
    order_date TEXT NOT NULL
)"""


def run_etl(source, database, report_path):
    raw = read_orders(source)
    good, bad, seen = [], [], set()
    for position, item in enumerate(raw, start=1):
        try:
            row = normalize(item)
            if row[0] in seen:
                raise DataError("duplicate order_id in this import")
            seen.add(row[0])
            good.append(row)
        except DataError as exc:
            bad.append({"row": position, "order_id": item.get("order_id") if isinstance(item, dict) else None, "reason": str(exc)})

    database = Path(database)
    report_path = Path(report_path)
    if database.resolve() == report_path.resolve():
        raise DataError("Database and JSON report paths must differ")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as conn:
        with conn:
            conn.execute(SCHEMA)
            conn.executemany("""INSERT INTO orders (order_id, customer, amount_cents, status, order_date)
                              VALUES (?, ?, ?, ?, ?)
                              ON CONFLICT(order_id) DO UPDATE SET
                                customer=excluded.customer, amount_cents=excluded.amount_cents,
                                status=excluded.status, order_date=excluded.order_date""", good)
        rows = conn.execute("SELECT order_id, customer, amount_cents, status, order_date FROM orders ORDER BY order_id").fetchall()
        grouped = conn.execute("""SELECT customer, COUNT(*), SUM(amount_cents) FROM orders
                                  WHERE status='paid' GROUP BY customer ORDER BY customer COLLATE NOCASE""").fetchall()
    paid = [row for row in rows if row[3] == "paid"]
    report = {
        "input_rows": len(raw), "accepted_rows": len(good), "rejected_rows": len(bad),
        "database_rows": len(rows), "paid_orders": len(paid),
        "pending_orders": sum(row[3] == "pending" for row in rows),
        "paid_total_usd": money(sum(row[2] for row in paid)),
        "paid_by_customer": [{"customer": c, "orders": n, "total_usd": money(total)} for c, n, total in grouped],
        "stored_orders": [{"order_id": oid, "customer": customer, "amount_usd": money(amount),
                           "status": status, "order_date": ordered} for oid, customer, amount, status, ordered in rows],
        "rejections": bad,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Load validated order JSON to SQLite and write JSON report")
    parser.add_argument("source", help="Orders JSON input")
    parser.add_argument("--database", default="output/orders.db")
    parser.add_argument("--report", default="output/report.json")
    args = parser.parse_args(argv)
    try:
        report = run_etl(args.source, args.database, args.report)
    except (DataError, sqlite3.Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ("input_rows", "accepted_rows", "rejected_rows", "database_rows", "paid_total_usd")}, indent=2))
    print(f"SQLite: {args.database}\nJSON report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
