"""Audit fictional purchase requests against a transparent approval policy."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

FIELDS = ("request_id", "submitted_date", "amount_usd", "status", "approver_role")
ROLES = {"none": 0, "staff": 1, "manager": 2, "director": 3}
STATUSES = {"pending", "approved", "rejected"}
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Issue:
    row: int
    request_id: str
    code: str
    detail: str


def required_role(amount: Decimal) -> int:
    if amount <= Decimal("500"):
        return 1
    if amount <= Decimal("5000"):
        return 2
    return 3


def audit_rows(rows: Iterable[dict[str, str]], as_of: date) -> list[Issue]:
    result: list[Issue] = []
    seen: set[str] = set()

    for rowno, row in enumerate(rows, start=2):
        data = {k: (row.get(k) or "").strip() for k in FIELDS}
        request = data["request_id"]

        def flag(code: str, detail: str) -> None:
            result.append(Issue(rowno, request, code, detail))

        missing = [field for field, value in data.items() if not value]
        if missing:
            for field in missing:
                flag("missing_field", field)
            continue

        folded = request.casefold()
        if folded in seen:
            flag("duplicate_request_id", request)
            continue
        seen.add(folded)

        try:
            submitted = date.fromisoformat(data["submitted_date"])
        except ValueError:
            flag("invalid_date", data["submitted_date"])
            continue

        if submitted > as_of:
            flag("future_submission", data["submitted_date"])

        try:
            amount = Decimal(data["amount_usd"])
            if not amount.is_finite() or amount <= 0 or amount != amount.quantize(CENT):
                raise InvalidOperation
        except InvalidOperation:
            flag("invalid_amount", data["amount_usd"])
            continue

        status = data["status"].casefold()
        role = data["approver_role"].casefold()
        if status not in STATUSES:
            flag("invalid_status", status)
            continue
        if role not in ROLES:
            flag("invalid_approver_role", role)
            continue

        if status == "approved" and ROLES[role] < required_role(amount):
            flag("insufficient_approval", f"amount={amount}; role={role}")
        if status == "pending" and (as_of - submitted).days > 14:
            flag("pending_over_14_days", f"submitted={submitted.isoformat()}")

    return result


def audit_file(source: Path, report: Path, as_of: date) -> list[Issue]:
    if source.resolve() == report.resolve():
        raise ValueError("Source and report paths must be different")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Missing required CSV headers")
        issues = audit_rows(reader, as_of)

    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "request_id", "code", "detail"])
        for issue in issues:
            writer.writerow([issue.row, issue.request_id, issue.code, issue.detail])
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD; no system-clock dependency")
    args = parser.parse_args(argv)
    try:
        as_of = date.fromisoformat(args.as_of)
        issues = audit_file(args.source, args.report, as_of)
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Found {len(issues)} issue(s); wrote {args.report}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
