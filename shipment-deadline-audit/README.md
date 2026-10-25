# Shipment Deadline and Event Consistency Audit

An offline Python 3.10+ auditor for reviewing shipping CSV exports
using fictional shipment IDs and an **explicit evaluation date**.
No live carrier API or personal customer data is needed.

## Problem

A fulfillment team wants to identify shipments that missed their
estimated delivery date, arrived late, or contain contradictory
tracking information.

Input fields:
`shipment_id,dispatched_date,eta_date,delivered_date,status`.

Statuses are `in_transit`, `delivered`, `cancelled`.
The delivered date may be blank when the shipment has not arrived.

The auditor flags overdue in-transit shipments, delivered-late events,
delivery dates before dispatch, ETAs earlier than dispatch, future
dispatch dates, missing delivery dates for completed shipments,
unexpected delivery dates for incomplete shipments, invalid dates,
unknown statuses, and duplicate shipment IDs.

## Run

```sh
python3 audit.py sample_shipments.csv issues.csv --as-of 2026-10-23
python3 -m unittest discover -s tests -v
```

The report contains `row,shipment_id,code,detail`.
Exit codes: 0 no issues, 1 issues found, 2 input error.

## Engineering notes

`audit_rows` is deterministic and separate from CSV input/output,
making it easy to unit test. Dates use the standard library's
`datetime.date`, avoiding wall-clock dependence. Deduplication
uses a case-insensitive set, giving average O(n) time and O(n)
memory for identifiers and issue records.

A late delivery is calculated from dates, not actual transit
durations. This is a demo auditing tool; it cannot determine carrier
fault, account for time zones, business days, holidays, or contractual
service levels.

## Follow-up exercise

Support a region-specific business-day SLA calendar and document
how it differs from simply comparing calendar dates.
