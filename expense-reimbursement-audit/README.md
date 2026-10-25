# Expense Reimbursement Policy Audit

An offline, repeatable Python 3.10+ CLI for reviewing fictional reimbursement
claims against explicit category caps. Uses only the standard library.

## Practical problem

Finance teams receive CSV claims with missing receipts, duplicates, and
unexpected amounts. This tool emits a row-level **issue report**, keeping the
source CSV unchanged.

Input columns: `claim_id,employee_id,receipt_id,date,category,currency,amount`.
Dates are ISO `YYYY-MM-DD`. The sample policy allows only **USD**, with caps
of meals **35**, travel **200**, and supplies **100**. The example is a teaching
policy, not a legal or company-specific expense rule.

The audit flags missing fields, repeated claim/receipt IDs (case-insensitive),
invalid dates and amounts, unsupported currencies, unknown categories,
nonpositive amounts, fractional cents, and claims above the category limit.
Money uses `decimal.Decimal` rather than binary floating point.

## Run

```sh
python3 audit.py sample_claims.csv issues.csv
cat issues.csv
python3 -m unittest discover -s tests -v
```

Exit codes: 0 means no issues, 1 means issues were reported, 2 means an
input or output error. The report is always a CSV with
`row,claim_id,code,detail` headers.

## Output interpretation

The sample detects an over-limit travel claim, a duplicate receipt and a
non-USD claim. Individual issues are not proof of fraud; they are checks for
human review. This does **not** convert currencies or connect to live systems.

## Architecture and limits

- `audit_claims` is a pure function for deterministic testing.
- `audit_file` handles CSV input/output and header validation.
- `main` handles CLI arguments and exit status.
- The checker runs in **O(n)** average time and uses **O(n)** memory for
  deduplication sets and its returned issues.
- Only the date syntax is validated, not whether a claim happened during
  an employee's service or whether a receipt is genuine.

## Next exercise

Read policy limits from a validated JSON file, and test reporting when
different departments use different approval thresholds.
