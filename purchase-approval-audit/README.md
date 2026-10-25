# Purchase Request Approval Audit

A self-contained Python 3.10+ CSV auditor demonstrating a **fictional,
explicit approval policy**. Data is offline and synthetic; no identities,
credentials or client exports are included.

## The problem

Finance administrators must review purchase requests for correct
approver authority, duplicate request IDs and long-running pending
requests. This project generates an auditable row-level issue report.

Required input CSV columns:
`request_id,submitted_date,amount_usd,status,approver_role`.

Rules for the example policy:
- Purchases up to USD 500 require staff or higher approval.
- Above USD 500 through 5,000 require a manager or director.
- Above USD 5,000 require a director.
- Pending requests older than **14 calendar days** are flagged.
- Approved requests lacking sufficient authority are flagged.
- Duplicates use case-insensitive request IDs; only the first is audited.
- Missing fields, invalid dates, nonfinite / nonpositive / fractional-cent
  amounts, invalid roles and unknown statuses are flagged.

The CLI requires an **explicit evaluation date** for repeatable results.
No exchange-rate conversion or real-world law/policy is implied.

## Run

```sh
python3 audit.py sample_requests.csv issues.csv --as-of 2026-10-24
python3 -m unittest discover -s tests -v
```

Output columns are `row,request_id,code,detail`.
Exit status: 0 clean; 1 report contains issues; 2 invalid input.
The example flags one insufficient approval and one overdue pending item.

## Design

`audit_rows` contains validation and policy logic without I/O.
`audit_file` reads and writes CSV, and `main` handles arguments
and exit codes. Money uses `decimal.Decimal` to avoid floating-point
surprises. The audit uses average O(n) time and O(n) memory for unique IDs
and issues.

**Limitations:** no fraud detection, document authenticity checks,
approval delegation, holiday calendar or currency conversion.

**Next exercise:** make approval thresholds configurable in a validated
JSON policy file and add tests for policy version changes.
