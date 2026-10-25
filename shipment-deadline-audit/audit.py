"""Audit synthetic shipment deadlines and delivery event consistency."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

FIELDS = ("shipment_id", "dispatched_date", "eta_date", "delivered_date", "status")
STATUSES = {"in_transit", "delivered", "cancelled"}


@dataclass(frozen=True)
class Issue:
    row: int
    shipment_id: str
    code: str
    detail: str


def audit_rows(rows: Iterable[dict[str, str]], as_of: date) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for rowno, source in enumerate(rows, start=2):
        data = {field: (source.get(field) or "").strip() for field in FIELDS}
        shipment = data["shipment_id"]

        def flag(code: str, detail: str) -> None:
            issues.append(Issue(rowno, shipment, code, detail))

        for required in ("shipment_id", "dispatched_date", "eta_date", "status"):
            if not data[required]:
                flag("missing_field", required)
        if any(not data[k] for k in ("shipment_id", "dispatched_date", "eta_date", "status")):
            continue

        folded = shipment.casefold()
        if folded in seen:
            flag("duplicate_shipment", shipment)
            continue
        seen.add(folded)

        try:
            dispatched = date.fromisoformat(data["dispatched_date"])
            eta = date.fromisoformat(data["eta_date"])
            delivered = (date.fromisoformat(data["delivered_date"])
                         if data["delivered_date"] else None)
        except ValueError:
            flag("invalid_date", "Expected ISO YYYY-MM-DD dates")
            continue

        status = data["status"].lower()
        if status not in STATUSES:
            flag("invalid_status", status)
            continue
        if eta < dispatched:
            flag("eta_before_dispatch", data["eta_date"])
        if dispatched > as_of:
            flag("future_dispatch", data["dispatched_date"])
        if delivered is not None and delivered < dispatched:
            flag("delivery_before_dispatch", data["delivered_date"])

        if status == "delivered":
            if delivered is None:
                flag("missing_delivery_date", "Status is delivered")
            elif delivered > eta:
                flag("delivered_late", f"{delivered.isoformat()} > {eta.isoformat()}")
        elif delivered is not None:
            flag("unexpected_delivery_date", f"Status is {status}")
        if status == "in_transit" and as_of > eta:
            flag("overdue_in_transit", f"ETA {eta.isoformat()} has passed")
    return issues


def audit_file(source: Path, report: Path, as_of: date) -> list[Issue]:
    if source.resolve() == report.resolve():
        raise ValueError("Source and report paths must be different")
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Missing required CSV columns")
        issues = audit_rows(reader, as_of)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "shipment_id", "code", "detail"])
        for issue in issues:
            writer.writerow([issue.row, issue.shipment_id, issue.code, issue.detail])
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--as-of", required=True, help="Evaluation date YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        as_of = date.fromisoformat(args.as_of)
        issues = audit_file(args.source, args.report, as_of)
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Found {len(issues)} issue(s); report: {args.report}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
