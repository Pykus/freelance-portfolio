"""Generate fictional input files for a reproducible payout audit demonstration."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ORDERS = (
    ("sample1", "USD", "100.00", "0.00", "5.00"),
    ("sample2", "USD", "80.00", "10.00", "4.00"),
    ("sample3", "EUR", "50.00", "0.00", "2.00"),
    ("sample4", "USD", "25.00", "0.00", "1.00"),
    ("sample5", "USD", "15.00", "0.00", "1.00"),
)

PAYOUTS = (
    ("sample1", "USD", "95.00"),
    ("sample2", "USD", "65.90"),
    ("sample3", "GBP", "48.00"),
    ("sample5", "USD", "14.00"),
    ("sample999", "USD", "5.00"),
)


def generate(output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    orders_path = output / "orders.csv"
    payouts_path = output / "payouts.csv"
    with orders_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("order_id", "currency", "gross", "refund", "fee"))
        writer.writerows(ORDERS)
    with payouts_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("order_id", "currency", "net_paid"))
        writer.writerows(PAYOUTS)
    return orders_path, payouts_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write two fictional sample CSVs")
    parser.add_argument("--output", type=Path, default=Path("examples"))
    args = parser.parse_args()
    orders, payouts = generate(args.output)
    print(f"Generated {orders} and {payouts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
