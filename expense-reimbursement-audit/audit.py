"""Audit fictional reimbursement claims against a small published policy."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

FIELDS = ("claim_id", "employee_id", "receipt_id", "date",
          "category", "currency", "amount")
LIMITS = {
    "meals": Decimal("35.00"),
    "travel": Decimal("200.00"),
    "supplies": Decimal("100.00"),
}
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Issue:
    row: int
    claim_id: str
    code: str
    detail: str


def audit_claims(rows: Iterable[dict[str, str]]) -> list[Issue]:
    issues: list[Issue] = []
    seen_receipts: set[str] = set()
    seen_claims: set[str] = set()

    for number, row in enumerate(rows, start=2):
        data = {key: (row.get(key) or "").strip() for key in FIELDS}
        claim = data["claim_id"]

        def flag(code: str, detail: str) -> None:
            issues.append(Issue(number, claim, code, detail))

        missing = [key for key, value in data.items() if not value]
        if missing:
            for field in missing:
                flag("missing_field", field)
            continue

        claim_key = claim.casefold()
        receipt_key = data["receipt_id"].casefold()
        if claim_key in seen_claims:
            flag("duplicate_claim", claim)
        else:
            seen_claims.add(claim_key)
        if receipt_key in seen_receipts:
            flag("duplicate_receipt", data["receipt_id"])
        else:
            seen_receipts.add(receipt_key)

        try:
            date.fromisoformat(data["date"])
        except ValueError:
            flag("invalid_date", data["date"])

        category = data["category"].casefold()
        if category not in LIMITS:
            flag("unknown_category", data["category"])
        if data["currency"] != "USD":
            flag("unsupported_currency", data["currency"])

        try:
            amount = Decimal(data["amount"])
            if not amount.is_finite():
                raise InvalidOperation
            if amount <= 0:
                flag("nonpositive_amount", data["amount"])
            if amount != amount.quantize(CENT):
                flag("fractional_cent", data["amount"])
            if category in LIMITS and amount > LIMITS[category]:
                flag("exceeds_policy_limit", f"{category}: {amount} > {LIMITS[category]}")
        except (InvalidOperation, ValueError):
            flag("invalid_amount", data["amount"])

    return issues


def audit_file(input_path: Path, output_path: Path) -> list[Issue]:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and report paths must differ")
    with input_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Input CSV is missing required columns")
        issues = audit_claims(reader)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "claim_id", "code", "detail"])
        for item in issues:
            writer.writerow([item.row, item.claim_id, item.code, item.detail])
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Claims CSV")
    parser.add_argument("output", type=Path, help="Issue report CSV")
    args = parser.parse_args(argv)
    try:
        issues = audit_file(args.input, args.output)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Audited claims; found {len(issues)} issue(s). Report: {args.output}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
