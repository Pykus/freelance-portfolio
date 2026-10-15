"""Offline, idempotent ingestion of synthetic RFC 822 order messages."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

REPORT_FIELDS = ("source_file", "status", "order_id", "total", "details")
MESSAGE_ID = re.compile(r"<[^<>\s]{1,198}>$")
ORDER_ID = re.compile(r"SO-[0-9]{4,8}$")
SKU = re.compile(r"[A-Z0-9][A-Z0-9_-]{1,23}$")
MONEY = re.compile(r"(?:0|[1-9][0-9]{0,7})\.[0-9]{2}$")
MAX_MESSAGE_BYTES = 1_000_000


class InvalidOrder(ValueError):
    """A message failed deterministic validation."""


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Order:
    message_id: str
    order_id: str
    sender: str
    customer: str
    items: tuple[LineItem, ...]

    @property
    def total_cents(self) -> int:
        return sum(item.quantity * item.unit_price_cents for item in self.items)


def message_text(message) -> str:
    """Read a text/plain body while ignoring HTML and file attachments."""
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if (part.get_content_type() == "text/plain"
                and part.get_content_disposition() != "attachment"):
            try:
                return part.get_content()
            except (UnicodeError, LookupError, ValueError) as error:
                raise InvalidOrder("text body cannot be decoded") from error
    raise InvalidOrder("no plain-text message body")


def parse_order(raw: bytes) -> Order:
    """Parse and validate one standalone email; never access a network."""
    message = BytesParser(policy=policy.default).parsebytes(raw)
    message_id = str(message.get("Message-ID", "")).strip()
    if not MESSAGE_ID.fullmatch(message_id):
        raise InvalidOrder("missing or invalid Message-ID")

    sender = parseaddr(str(message.get("From", "")))[1]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", sender):
        raise InvalidOrder("invalid sender address")
    if not str(message.get("Subject", "")).lower().startswith("order"):
        raise InvalidOrder("subject must begin with Order")

    values: dict[str, str] = {}
    items: list[LineItem] = []
    for original_line in message_text(message).splitlines():
        line = original_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise InvalidOrder("unrecognized line without a colon")
        key, value = key.strip().lower(), value.strip()
        if key == "item":
            fields = [field.strip() for field in value.split(",")]
            if len(fields) != 3:
                raise InvalidOrder("Item requires SKU, quantity and unit price")
            sku, quantity, price = fields
            if not SKU.fullmatch(sku):
                raise InvalidOrder("invalid item SKU")
            if not re.fullmatch(r"[0-9]{1,5}", quantity):
                raise InvalidOrder("quantity must be a positive whole number")
            count = int(quantity)
            if not (1 <= count <= 10000):
                raise InvalidOrder("quantity is outside allowed range")
            if not MONEY.fullmatch(price):
                raise InvalidOrder("price must be nonnegative with two decimals")
            cents = int(Decimal(price) * 100)
            items.append(LineItem(sku, count, cents))
        elif key in ("order-id", "customer"):
            if key in values:
                raise InvalidOrder("duplicate order field: " + key)
            values[key] = value
        else:
            raise InvalidOrder("unknown field: " + key)

    order_id = values.get("order-id", "")
    customer = values.get("customer", "")
    if not ORDER_ID.fullmatch(order_id):
        raise InvalidOrder("missing or invalid Order-ID")
    if not customer or len(customer) > 120 or any(ord(c) < 32 for c in customer):
        raise InvalidOrder("invalid Customer")
    if not items:
        raise InvalidOrder("at least one Item is required")
    return Order(message_id, order_id, sender, customer, tuple(items))


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            message_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL UNIQUE,
            sender TEXT NOT NULL,
            customer TEXT NOT NULL,
            total_cents INTEGER NOT NULL,
            source_file TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_lines (
            message_id TEXT NOT NULL REFERENCES orders(message_id),
            line_no INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL,
            PRIMARY KEY (message_id, line_no)
        );
    """)
    return connection


def record_order(connection: sqlite3.Connection, order: Order, source: str) -> tuple[str, str]:
    """Write an entire order and its lines in one SQLite transaction."""
    if connection.execute(
        "SELECT 1 FROM orders WHERE message_id = ?", (order.message_id,)
    ).fetchone():
        return "duplicate", "Message-ID already imported"
    if connection.execute(
        "SELECT 1 FROM orders WHERE order_id = ?", (order.order_id,)
    ).fetchone():
        return "duplicate", "Order-ID already imported"
    with connection:
        connection.execute(
            """INSERT INTO orders
            (message_id, order_id, sender, customer, total_cents, source_file)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (order.message_id, order.order_id, order.sender, order.customer,
             order.total_cents, source),
        )
        connection.executemany(
            """INSERT INTO order_lines
            (message_id, line_no, sku, quantity, unit_price_cents)
            VALUES (?, ?, ?, ?, ?)""",
            (
                (order.message_id, number, item.sku, item.quantity, item.unit_price_cents)
                for number, item in enumerate(order.items, start=1)
            ),
        )
    return "imported", f"{len(order.items)} line item(s)"


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    """Replace a report atomically so partial CSV output is not mistaken for success."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=path.parent,
            prefix=".report-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def ingest(directory: Path, database: Path, report: Path) -> dict[str, int]:
    if not directory.is_dir():
        raise ValueError("input must be an existing directory")
    rows: list[dict[str, str]] = []
    counts = {"imported": 0, "duplicate": 0, "rejected": 0}
    with connect(database) as connection:
        for path in sorted(directory.glob("*.eml")):
            order_id, total = "", ""
            try:
                if path.stat().st_size > MAX_MESSAGE_BYTES:
                    raise InvalidOrder("message exceeds 1 MB limit")
                order = parse_order(path.read_bytes())
                order_id = order.order_id
                total = f"{Decimal(order.total_cents) / 100:.2f}"
                status, details = record_order(connection, order, path.name)
            except (InvalidOrder, OSError) as error:
                status, details = "rejected", str(error)
            counts[status] += 1
            rows.append(dict(source_file=path.name, status=status,
                             order_id=order_id, total=total, details=details))
    write_report(report, rows)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="directory of .eml files")
    parser.add_argument("--db", required=True, type=Path, help="persistent SQLite database")
    parser.add_argument("--report", required=True, type=Path, help="output CSV report")
    args = parser.parse_args(argv)
    try:
        counts = ingest(args.input, args.db, args.report)
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
