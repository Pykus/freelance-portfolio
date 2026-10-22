"""Offline contract renewal and notice deadline review."""

import argparse
import csv
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ("contract_id", "vendor", "start_date", "end_date", "notice_days",
          "auto_renew", "annual_amount", "currency", "status")
REPORT_FIELDS = ("row_number", "contract_id", "vendor", "end_date",
                 "notice_deadline", "issue_codes")


class DataError(ValueError):
    pass


def iso_date(value):
    try:
        result = date.fromisoformat(value)
        return result if result.isoformat() == value else None
    except (TypeError, ValueError):
        return None


def money(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def load_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, restkey="_extra_cells")
        header = reader.fieldnames
        if not header or len(header) != len(set(header)):
            raise DataError("Missing or repeated CSV header names")
        missing = [name for name in FIELDS if name not in header]
        if missing:
            raise DataError("Missing required fields: " + ", ".join(missing))
        records = []
        for line, raw in enumerate(reader, 2):
            malformed = raw.get("_extra_cells") is not None or any(
                raw[name] is None for name in FIELDS
            )
            item = {name: (raw[name] or "").strip() for name in FIELDS}
            records.append({"line": line, "data": item,
                            "codes": ["MALFORMED_ROW"] if malformed else [],
                            "deadline": None, "valid": False, "amount": None})
    return records


def review(records, today, horizon=30):
    if not 0 <= horizon <= 3650:
        raise ValueError("Review horizon must be between 0 and 3650 days")
    identifiers = defaultdict(list)
    for row in records:
        d, issues = row["data"], row["codes"]
        key = d["contract_id"].strip().casefold()
        if key:
            identifiers[key].append(row)
        else:
            issues.append("MISSING_CONTRACT_ID")
        if not d["vendor"]:
            issues.append("MISSING_VENDOR")
        start, end = iso_date(d["start_date"]), iso_date(d["end_date"])
        if start is None:
            issues.append("INVALID_START_DATE")
        if end is None:
            issues.append("INVALID_END_DATE")
        if start and end and end < start:
            issues.append("END_BEFORE_START")
        notice_text = d["notice_days"]
        notice = int(notice_text) if re.fullmatch(r"[0-9]{1,5}", notice_text) else None
        if notice is None or not 0 <= notice <= 3650:
            issues.append("INVALID_NOTICE_DAYS")
        renewing = d["auto_renew"].casefold()
        if renewing not in ("yes", "no"):
            issues.append("INVALID_AUTO_RENEW")
        amount = money(d["annual_amount"])
        row["amount"] = amount
        if amount is None:
            issues.append("INVALID_AMOUNT")
        if not re.fullmatch(r"[A-Za-z]{3}", d["currency"]):
            issues.append("INVALID_CURRENCY")
        status = d["status"].casefold()
        if status not in ("active", "terminated"):
            issues.append("INVALID_STATUS")
        row["valid"] = not issues
        if issues:
            continue
        row["deadline"] = end - timedelta(days=notice)
        if status == "terminated":
            continue
        if end < today:
            issues.append("EXPIRED_ACTIVE")
        elif end <= today + timedelta(days=horizon):
            issues.append("EXPIRING_SOON")
        if renewing == "yes" and today <= end:
            if today > row["deadline"]:
                issues.append("NOTICE_DEADLINE_PASSED")
            elif row["deadline"] <= today + timedelta(days=horizon):
                issues.append("NOTICE_DUE_SOON")
    for group in identifiers.values():
        if len(group) > 1:
            for row in group:
                row["codes"].append("DUPLICATE_CONTRACT_ID")
                row["valid"] = False
    return records


def summary(records, today, horizon):
    counts = Counter(issue for row in records for issue in row["codes"])
    recurring = defaultdict(Decimal)
    for row in records:
        d = row["data"]
        if row["valid"] and d["status"].casefold() == "active":
            recurring[d["currency"].upper()] += row["amount"]
    return {
        "as_of": today.isoformat(),
        "horizon_days": horizon,
        "rows_reviewed": len(records),
        "rows_flagged": sum(bool(row["codes"]) for row in records),
        "issue_counts": dict(sorted(counts.items())),
        "active_annual_amount_by_currency": {
            code: str(amount) for code, amount in sorted(recurring.items())
        },
    }


def spreadsheet_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def replace_atomically(path, writer):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         newline="", dir=path.parent,
                                         prefix=".audit-", delete=False) as stream:
            temp = stream.name
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def save(records, today, horizon, csv_path, json_path):
    if Path(csv_path).resolve() == Path(json_path).resolve():
        raise ValueError("Output paths must differ")
    report = summary(records, today, horizon)

    def write_csv(stream):
        writer = csv.DictWriter(stream, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in records:
            if not row["codes"]:
                continue
            d = row["data"]
            writer.writerow({
                "row_number": row["line"],
                "contract_id": spreadsheet_safe(d["contract_id"]),
                "vendor": spreadsheet_safe(d["vendor"]),
                "end_date": d["end_date"],
                "notice_deadline": row["deadline"].isoformat()
                if row["deadline"] else "",
                "issue_codes": ";".join(row["codes"]),
            })

    replace_atomically(csv_path, write_csv)
    replace_atomically(json_path, lambda stream:
                       json.dump(report, stream, indent=2, sort_keys=True))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--findings", type=Path, default=Path("findings.csv"))
    parser.add_argument("--summary", type=Path, default=Path("summary.json"))
    args = parser.parse_args(argv)
    today = iso_date(args.as_of)
    if today is None:
        parser.error("--as-of requires YYYY-MM-DD")
    if not 0 <= args.horizon <= 3650:
        parser.error("--horizon must be between 0 and 3650")
    try:
        records = review(load_csv(args.input), today, args.horizon)
        result = save(records, today, args.horizon, args.findings, args.summary)
    except (OSError, DataError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
