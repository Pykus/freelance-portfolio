# CSV Reconciliation: A Python Portfolio Demo

Compare two fictional CSV exports by a stable ID. Detect added, removed, changed and unchanged records even when rows are reordered.

## Quick start

Python 3.10+; no external dependencies. Create `before.csv` and `after.csv` with columns `id,amount`, then run:

```sh
python reconcile.py before.csv after.csv
python -m unittest discover -s . -p test_reconcile.py -v
```

For example, before contains IDs 001=1.00, 002=2.00, 004=4.00; after contains 001=1.00, 002=3.00, 003=3.00. The result is added 003, removed 004, changed 002, unchanged 1.

## Design

IDs are strings, preserving leading zeros. Decimal amounts avoid binary floating-point rounding. Duplicate IDs, nonfinite amounts and more than two decimal places are rejected. Input must have `id,amount` columns.

## Scope

The examples use synthetic data. This tool is designed for two-column exports and is not a complete accounting or audit system.
