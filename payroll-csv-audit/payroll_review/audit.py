"""Read payroll records and collect review findings."""
import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .checks import evaluate_row, validate_headers


def analyze(path, overtime_limit=Decimal("20")):
    if not overtime_limit.is_finite() or overtime_limit < 0:
        raise ValueError("Invalid overtime threshold")
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        headers = validate_headers(reader.fieldnames)
        records = []
        first_seen = {}
        for index, source_row in enumerate(reader, start=2):
            row = {column: source_row.get(column) or "" for column in headers}
            codes = evaluate_row(row, overtime_limit)
            if None in source_row or any(source_row.get(h) is None for h in headers):
                codes.append("MALFORMED_ROW")
            identifier = row["employee_id"].strip().casefold()
            if identifier:
                if identifier in first_seen:
                    codes.append("DUPLICATE_EMPLOYEE_ID")
                    first = records[first_seen[identifier]]
                    if "DUPLICATE_EMPLOYEE_ID" not in first["issue_codes"]:
                        first["issue_codes"].append("DUPLICATE_EMPLOYEE_ID")
                else:
                    first_seen[identifier] = len(records)
            records.append({"row_number": index, "source": row, "issue_codes": codes})
    flagged = [record for record in records if record["issue_codes"]]
    counts = Counter(code for item in flagged for code in item["issue_codes"])
    summary = {
        "total_rows": len(records),
        "valid_rows": len(records) - len(flagged),
        "issue_rows": len(flagged),
        "issue_counts": dict(sorted(counts.items())),
    }
    return headers, flagged, summary
