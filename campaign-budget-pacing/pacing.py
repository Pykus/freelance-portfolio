"""Audit fictional daily advertising spend against planned campaign budgets."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

REQUIRED = ("campaign_id", "date", "budget_usd", "spend_usd")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Issue:
    row: int
    campaign_id: str
    date: str
    code: str
    detail: str


@dataclass(frozen=True)
class Summary:
    campaign_id: str
    days: int
    budget_usd: Decimal
    spend_usd: Decimal
    variance_usd: Decimal
    utilization_pct: Decimal


@dataclass(frozen=True)
class AuditResult:
    issues: list[Issue]
    summaries: list[Summary]


def money(value: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(value)
        if not number.is_finite() or number != number.quantize(CENT):
            raise ValueError("Amount must be finite and have at most two decimal places")
        if number < 0 or (positive and number == 0):
            raise ValueError("Amount must be nonnegative; budgets must be positive")
        return number
    except InvalidOperation as error:
        raise ValueError("Invalid monetary amount") from error


def audit_rows(rows: Iterable[dict[str, str]]) -> AuditResult:
    issues: list[Issue] = []
    seen: set[tuple[str, date]] = set()
    by_campaign: dict[str, list[tuple[date, int, Decimal, Decimal]]] = {}

    for rowno, row in enumerate(rows, start=2):
        raw = {key: (row.get(key) or "").strip() for key in REQUIRED}
        campaign_id = raw["campaign_id"]

        def flag(code: str, detail: str) -> None:
            issues.append(Issue(rowno, campaign_id, raw["date"], code, detail))

        missing = [key for key, value in raw.items() if not value]
        if missing:
            for field in missing:
                flag("missing_field", field)
            continue

        try:
            day = date.fromisoformat(raw["date"])
        except ValueError:
            flag("invalid_date", raw["date"])
            continue
        try:
            budget = money(raw["budget_usd"], positive=True)
            spend = money(raw["spend_usd"])
        except ValueError as error:
            flag("invalid_amount", str(error))
            continue

        key = (campaign_id.casefold(), day)
        if key in seen:
            flag("duplicate_day", "Only the first valid daily record counts")
            continue
        seen.add(key)

        if spend > budget:
            flag("daily_overspend", f"{spend} > {budget}")
        by_campaign.setdefault(campaign_id.casefold(), []).append(
            (day, rowno, budget, spend)
        )

    summaries: list[Summary] = []
    for campaign, observations in sorted(by_campaign.items()):
        running_budget = Decimal("0")
        running_spend = Decimal("0")
        for day, rowno, budget, spend in sorted(observations):
            running_budget += budget
            running_spend += spend
            if running_spend > running_budget:
                issues.append(Issue(
                    rowno, campaign, day.isoformat(), "cumulative_overspend",
                    f"{running_spend} > {running_budget}",
                ))
        summaries.append(Summary(
            campaign, len(observations), running_budget, running_spend,
            running_budget - running_spend,
            (running_spend * 100 / running_budget).quantize(CENT),
        ))

    issues.sort(key=lambda item: (item.row, item.code))
    return AuditResult(issues, summaries)


def audit_file(input_path: Path, issues_path: Path, summary_path: Path) -> AuditResult:
    if len({p.resolve() for p in (input_path, issues_path, summary_path)}) != 3:
        raise ValueError("Input, issue report, and summary paths must be distinct")
    with input_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(REQUIRED).issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns")
        result = audit_rows(reader)

    for target in (issues_path, summary_path):
        target.parent.mkdir(parents=True, exist_ok=True)
    with issues_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "campaign_id", "date", "code", "detail"])
        for item in result.issues:
            writer.writerow([item.row, item.campaign_id, item.date, item.code, item.detail])
    with summary_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "campaign_id", "days", "budget_usd", "spend_usd",
            "variance_usd", "utilization_pct",
        ])
        for s in result.summaries:
            writer.writerow([
                s.campaign_id, s.days, s.budget_usd, s.spend_usd,
                s.variance_usd, s.utilization_pct,
            ])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("issues", type=Path)
    parser.add_argument("summary", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_file(args.input, args.issues, args.summary)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"{len(result.summaries)} campaign(s), {len(result.issues)} issue(s)")
    return 1 if result.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
