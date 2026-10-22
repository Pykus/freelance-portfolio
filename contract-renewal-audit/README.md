# Contract Renewal Notice Auditor

A command-line Python tool for tracking contract end dates and notice windows based on an approved structured CSV register. It is designed for routine administrative review, using only the Python standard library.

## Capabilities

- Validate required fields, strict ISO dates, finite nonnegative monetary amounts, notice periods, and agreement statuses.
- Detect missing and duplicate agreement identifiers, flagging every occurrence of a duplicate.
- Distinguish agreements nearing their notice deadline, notice deadlines already passed, agreements nearing expiry, and active agreements already expired.
- Suppress notice alerts for nonrenewing agreements and all business alerts for terminated agreements.
- Aggregate valid active annual amounts by currency with Decimal arithmetic and no exchange-rate assumptions.
- Produce reproducible flagged-row CSV and structured JSON summaries.
- Escape dangerous spreadsheet formulas in exported free-text fields, and replace outputs atomically per file.

## Usage

Python 3.11 or newer is required. From this directory:

    python3 contract_audit.py examples/contracts.csv --as-of 2026-10-22 --horizon 45 --findings findings.csv --summary summary.json
    python3 -m unittest discover -s tests -v

The as-of date is mandatory. The horizon defaults to 30 calendar days, inclusive.

## Input schema

| Field | Example | Notes |
| :--- | :--- | :--- |
| contract_id | A-100 | Unique identifier, case-insensitive |
| vendor | Example Hosting | Supplier |
| start_date | 2026-01-01 | ISO date |
| end_date | 2026-12-31 | Current term end |
| notice_days | 60 | Whole calendar days (0 to 3650) |
| auto_renew | yes | yes or no |
| annual_amount | 1200.50 | Nonnegative finite decimal |
| currency | USD | Three alphabetic characters |
| status | active | active or terminated |

Extra columns are ignored. CSVs may include a UTF-8 BOM. Records with malformed or invalid fields are flagged and excluded from nominal annual totals.

## Review codes

| Code | Meaning |
| :--- | :--- |
| NOTICE_DUE_SOON | Notice deadline is today or within the horizon |
| NOTICE_DEADLINE_PASSED | Notice deadline passed before the term ends |
| EXPIRING_SOON | Agreement end date falls within the horizon |
| EXPIRED_ACTIVE | Agreement remains active past its stated end |
| DUPLICATE_CONTRACT_ID | Identifier appears more than once |
| END_BEFORE_START | Inconsistent contract dates |
| INVALID_* or MISSING_* | Missing or invalid structured input |
| MALFORMED_ROW | Unexpected number of CSV columns |

A row may have multiple findings. Deadline = end_date minus notice_days, without business-day or holiday adjustments.

## Interpretation

Notice findings indicate records requiring human review, not that cancellation is legally possible. The tool does not parse contracts, determine actual notice law, determine automatic-renewal rights, or send notices. Annual totals are nominal amounts for valid active records, not forecasts or currency-converted exposure. Reports are individually atomically replaced but are not a transactional two-file pair. The entire register is kept in memory.

All sample data is synthetic.
