"""Track changes in small HTML product catalogs using deterministic SQLite history.

Offline by design: callers provide saved HTML snapshots instead of fetching websites.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_MONEY = re.compile(r"(?:\$|USD\s+)?([0-9]+)\.([0-9]{2})\Z")


class SnapshotError(ValueError):
    """Invalid catalog content or inconsistent snapshot history."""


class CatalogParser(HTMLParser):
    """Extract article[data-item-id] with an h2 title and span.price amount."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "article":
            if self._current is not None:
                raise SnapshotError("Nested article elements are not supported")
            item_id = attributes.get("data-item-id")
            if item_id is not None:
                self._current = {"item_id": item_id, "title": "", "price": ""}
                self._field = None
        elif self._current is not None:
            if tag == "h2":
                if self._current["title"]:
                    raise SnapshotError("An item has multiple titles")
                self._field = "title"
            elif tag == "span" and "price" in attributes.get("class", "").split():
                if self._current["price"]:
                    raise SnapshotError("An item has multiple prices")
                self._field = "price"

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._field is not None:
            self._current[self._field] += data

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "article":
            self.records.append(self._current)
            self._current = None
            self._field = None
        elif tag == "h2" and self._field == "title":
            self._field = None
        elif tag == "span" and self._field == "price":
            self._field = None


def parse_catalog(html: str) -> dict[str, dict[str, Any]]:
    parser = CatalogParser()
    parser.feed(html)
    parser.close()
    if parser._current is not None:
        raise SnapshotError("Unclosed item article")
    if not parser.records:
        raise SnapshotError("No catalog items found")

    items: dict[str, dict[str, Any]] = {}
    for record in parser.records:
        item_id = record["item_id"].strip()
        title = " ".join(record["title"].split())
        price = " ".join(record["price"].split())
        if not _ID.fullmatch(item_id):
            raise SnapshotError("Invalid item identifier")
        if not title:
            raise SnapshotError(f"Missing title for {item_id}")
        match = _MONEY.fullmatch(price)
        if not match:
            raise SnapshotError(f"Invalid price for {item_id}: {price!r}")
        cents = int(match.group(1)) * 100 + int(match.group(2))
        if cents > 1_000_000_000:
            raise SnapshotError(f"Price out of range for {item_id}")
        if item_id in items:
            raise SnapshotError(f"Duplicate item identifier: {item_id}")
        items[item_id] = {"item_id": item_id, "title": title, "price_cents": cents}
    return dict(sorted(items.items()))


def _init_db(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            name TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            UNIQUE(source, name)
        );
        CREATE TABLE IF NOT EXISTS items (
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
            item_id TEXT NOT NULL,
            title TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            PRIMARY KEY(snapshot_id, item_id)
        );
    """)


def _items_at(connection: sqlite3.Connection, snapshot_id: int | None) -> dict[str, dict[str, Any]]:
    if snapshot_id is None:
        return {}
    rows = connection.execute(
        "SELECT item_id, title, price_cents FROM items WHERE snapshot_id = ? ORDER BY item_id",
        (snapshot_id,),
    ).fetchall()
    return {item_id: {"item_id": item_id, "title": title, "price_cents": cents}
            for item_id, title, cents in rows}


def run_snapshot(database: Path, source: str, name: str, html: str) -> dict[str, Any]:
    """Validate, store once, and return a deterministic comparison report."""
    if not _NAME.fullmatch(source) or not _NAME.fullmatch(name):
        raise SnapshotError("Source and snapshot names must be short ASCII identifiers")
    current = parse_catalog(html)
    canonical = json.dumps(list(current.values()), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        _init_db(connection)
        with connection:
            existing = connection.execute(
                "SELECT id, fingerprint FROM snapshots WHERE source=? AND name=?",
                (source, name),
            ).fetchone()
            if existing is not None:
                snapshot_id, previous_digest = existing
                if previous_digest != digest:
                    raise SnapshotError("Snapshot name already exists with different records")
                already_recorded = True
                previous = connection.execute(
                    "SELECT id FROM snapshots WHERE source=? AND id<? ORDER BY id DESC LIMIT 1",
                    (source, snapshot_id),
                ).fetchone()
            else:
                previous = connection.execute(
                    "SELECT id FROM snapshots WHERE source=? ORDER BY id DESC LIMIT 1",
                    (source,),
                ).fetchone()
                cursor = connection.execute(
                    "INSERT INTO snapshots(source, name, fingerprint) VALUES (?, ?, ?)",
                    (source, name, digest),
                )
                snapshot_id = cursor.lastrowid
                connection.executemany(
                    "INSERT INTO items(snapshot_id, item_id, title, price_cents) VALUES (?, ?, ?, ?)",
                    [(snapshot_id, item["item_id"], item["title"], item["price_cents"])
                     for item in current.values()],
                )
                already_recorded = False
            before = _items_at(connection, previous[0] if previous else None)

    changes: list[dict[str, Any]] = []
    for item_id in sorted(set(before) | set(current)):
        old, new = before.get(item_id), current.get(item_id)
        status = "added" if old is None else "removed" if new is None else "unchanged" if old == new else "updated"
        changes.append({"item_id": item_id, "status": status, "before": old, "after": new})
    counts = {status: sum(c["status"] == status for c in changes)
              for status in ("added", "updated", "removed", "unchanged")}
    return {"source": source, "snapshot": name, "already_recorded": already_recorded,
            "current_count": len(current), "counts": counts, "changes": changes,
            "current_items": list(current.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path, help="Saved HTML catalog")
    parser.add_argument("--database", required=True, type=Path, help="SQLite history file")
    parser.add_argument("--source", required=True, help="Stable source identifier")
    parser.add_argument("--snapshot", required=True, help="Unique snapshot identifier")
    parser.add_argument("--output", required=True, type=Path, help="Report JSON destination")
    args = parser.parse_args(argv)
    try:
        html = args.html.read_text(encoding="utf-8")
        result = run_snapshot(args.database, args.source, args.snapshot, html)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Atomically replace the report to avoid exposing partial JSON.
        temporary = args.output.with_name(args.output.name + ".tmp")
        try:
            temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(args.output)
        finally:
            temporary.unlink(missing_ok=True)
        print(json.dumps({"snapshot": args.snapshot, "counts": result["counts"],
                          "already_recorded": result["already_recorded"]}))
        return 0
    except (SnapshotError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
