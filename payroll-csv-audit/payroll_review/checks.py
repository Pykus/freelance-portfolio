"""Row-level payroll CSV validation using exact decimal arithmetic."""
from decimal import Decimal, InvalidOperation

REQUIRED = (
    "employee_id", "store", "contracted_hours", "worked_hours",
    "overtime_hours", "sick_hours", "vacation_hours", "hourly_rate", "bonus",
)
NUMERIC = REQUIRED[2:]


def positive_decimal(text):
    try:
        value = Decimal(text.strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return value if value.is_finite() and value >= 0 else None


def validate_headers(headers):
    if not headers:
        raise ValueError("Missing CSV header")
    if any(not header for header in headers) or len(headers) != len(set(headers)):
        raise ValueError("Blank or duplicate CSV header")
    missing = sorted(set(REQUIRED) - set(headers))
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    if "row_number" in headers or "issue_codes" in headers:
        raise ValueError("Reserved output column name")
    return headers


def evaluate_row(row, overtime_limit):
    codes = []
    if not row["employee_id"].strip():
        codes.append("MISSING_EMPLOYEE_ID")
    if not row["store"].strip():
        codes.append("MISSING_STORE")
    numbers = {}
    for column in NUMERIC:
        value = positive_decimal(row[column])
        if value is None:
            codes.append("INVALID_" + column.upper())
        else:
            numbers[column] = value
    overtime = numbers.get("overtime_hours")
    worked = numbers.get("worked_hours")
    if overtime is not None and overtime > overtime_limit:
        codes.append("HIGH_OVERTIME")
    if overtime is not None and worked is not None and overtime > worked:
        codes.append("OVERTIME_EXCEEDS_WORKED")
    for column in ("contracted_hours", "worked_hours", "overtime_hours",
                   "sick_hours", "vacation_hours"):
        if numbers.get(column, Decimal(0)) > 744:
            codes.append("IMPLAUSIBLE_" + column.upper())
    return codes
