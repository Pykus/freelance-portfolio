# JSON Orders → SQLite ETL

A small, reproducible Python ETL pipeline for fictional sales orders. It reads a JSON export, validates and normalizes records, **writes accepted records into a real SQLite database**, and **writes an audit/analytics report to a separate JSON file**. The terminal summary is not the output dataset. This is a portfolio demonstration, not an implementation for an actual client.

## Business problem

A business receives order exports containing inconsistent names, invalid amounts, and duplicate order IDs. It wants a queryable database, consistent monetary values, a customer-level revenue summary, and an audit trail of rejected records. This demo uses the Python standard library only (Python 3.9+).

## Features

- **Extract:** load an `orders` array from an input JSON file and reject malformed root documents.
- **Transform:** validate required columns, IDs, ISO dates, positive USD amounts with no more than two decimals, and `paid`/`pending` status; trim surrounding customer-name spaces. Preserve amounts exactly as **integer cents** rather than floats.
- **Validate:** reject bad or repeated IDs *within the current import* with per-row reasons; continue importing valid rows.
- **Load:** create SQLite `orders` table with a primary key and constraints; use parameterized SQL and UPSERT (repeat imports update existing records without duplicating them).
- **Report:** query actual persisted database rows, total paid USD, paid/pending counts, and paid revenue grouped by customer. Include accepted/rejected counts, stored rows, and rejection details.

## Complete example — original input

This is the entire committed [`examples/orders.json`](examples/orders.json) file (seven orders, all fictional):

```json
{
  "orders": [
    {"order_id": "O-101", "customer": " Alpha LLC ", "amount_usd": "125.50", "status": "paid", "order_date": "2026-09-01"},
    {"order_id": "O-102", "customer": "Beta Ltd", "amount_usd": "80.00", "status": "pending", "order_date": "2026-09-02"},
    {"order_id": "O-103", "customer": "Alpha LLC", "amount_usd": "40.00", "status": "paid", "order_date": "2026-09-03"},
    {"order_id": "O-104", "customer": "Gamma Co", "amount_usd": "-5.00", "status": "paid", "order_date": "2026-09-04"},
    {"order_id": "O-105", "customer": "Beta Ltd", "amount_usd": "oops", "status": "paid", "order_date": "2026-09-05"},
    {"order_id": "O-106", "customer": "Beta Ltd", "amount_usd": "50.25", "status": "paid", "order_date": "2026-09-06"},
    {"order_id": "O-101", "customer": "Alpha LLC", "amount_usd": "125.50", "status": "paid", "order_date": "2026-09-01"}
  ]
}
```

## Run (from this folder)

```bash
python etl.py examples/orders.json --database output/orders.db --report output/report.json
```

`output/` is created if absent. The command writes **two real output files**:

1. `output/orders.db` — a **binary SQLite database**, created on the first run, then *updated* in place on subsequent runs. It contains `orders` rows, not just aggregate statistics.
2. `output/report.json` — a **text JSON report**, created or **overwritten** on each run. It describes the persisted database after the import and rejected input records.

The original input, committed expected report, and source code are **not modified**. `output/` is excluded by `.gitignore`.

### How every source record is handled

| Input row | Result | Explanation |
| --- | --- | --- |
| 1 (`O-101`) | Stored | Name trimmed from ` Alpha LLC ` to `Alpha LLC`; paid $125.50 |
| 2 (`O-102`) | Stored | Pending $80.00; excluded from paid revenue |
| 3 (`O-103`) | Stored | Paid $40.00 |
| 4 (`O-104`) | Rejected | Negative amount -$5.00 |
| 5 (`O-105`) | Rejected | `oops` is not a valid decimal amount |
| 6 (`O-106`) | Stored | Paid $50.25 |
| 7 (`O-101`) | Rejected | Duplicate order ID within the input batch |

Thus **7 input = 4 accepted + 3 rejected**; SQLite holds **4** orders. Three paid orders total **$215.75** ($125.50 + $40.00 + $50.25). One pending order is excluded from revenue.

### Actual output report (complete values)

The JSON written to `output/report.json` matches the committed regression fixture [`examples/expected-report.json`](examples/expected-report.json):

```json
{
  "input_rows": 7,
  "accepted_rows": 4,
  "rejected_rows": 3,
  "database_rows": 4,
  "paid_orders": 3,
  "pending_orders": 1,
  "paid_total_usd": "215.75",
  "paid_by_customer": [
    {"customer": "Alpha LLC", "orders": 2, "total_usd": "165.50"},
    {"customer": "Beta Ltd", "orders": 1, "total_usd": "50.25"}
  ],
  "stored_orders": [
    {"order_id": "O-101", "customer": "Alpha LLC", "amount_usd": "125.50", "status": "paid", "order_date": "2026-09-01"},
    {"order_id": "O-102", "customer": "Beta Ltd", "amount_usd": "80.00", "status": "pending", "order_date": "2026-09-02"},
    {"order_id": "O-103", "customer": "Alpha LLC", "amount_usd": "40.00", "status": "paid", "order_date": "2026-09-03"},
    {"order_id": "O-106", "customer": "Beta Ltd", "amount_usd": "50.25", "status": "paid", "order_date": "2026-09-06"}
  ],
  "rejections": [
    {"row": 4, "order_id": "O-104", "reason": "amount_usd must be greater than zero and at most 1000000"},
    {"row": 5, "order_id": "O-105", "reason": "invalid amount_usd"},
    {"row": 7, "order_id": "O-101", "reason": "duplicate order_id in this import"}
  ]
}
```

The generated JSON has expanded indentation; the values and arrays above are identical. The `stored_orders` list is a SELECT from SQLite and demonstrates the four **actual rows in the database**. You can inspect or query `output/orders.db` with DB Browser for SQLite or Python's `sqlite3` library.

## Tests

```bash
python -m unittest discover -s tests -v
```

The 8 tests cover: complete fixture-to-database-to-report agreement; CLI creating both files; idempotent reruns; SQL upsert updating an existing order; safe handling of quoted customer names; malformed input; invalid dates; and invalid monetary amounts. No third-party packages, network access, or genuine customer data are involved.

## File effects, limitations, and safety

`etl.py` is the CLI and SQLite loader, `validation.py` is the input validator, and `tests/` contains automated tests. `examples/orders.json` is the unchanged input; `examples/expected-report.json` is a committed read-only regression fixture. The program creates/updates `output/orders.db` and creates/overwrites `output/report.json` and may create their parent directories. Never set the same path for database and report.

This demo handles **USD only**, supports two order statuses, and requires a particular JSON schema. It does not connect to a live API, use AI, schedule jobs, or substitute for PostgreSQL, Airflow, or production deployment. Reimports UPSERT existing IDs but **do not delete** stale IDs absent from later files; reporting summarizes the entire existing database, which may therefore differ from the latest input batch. SQLite commit occurs before the report is written; if report writing fails, the database may still contain the committed changes. Review and extend these behaviors for real business use.
