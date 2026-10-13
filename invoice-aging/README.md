# Invoice Aging Report

A small Python command-line tool that groups outstanding invoices by days past due. Useful for reviewing receivables from an exported invoice CSV.

## Input
CSV columns: `invoice_id,due_date,amount`. Dates use ISO `YYYY-MM-DD`, and amounts use decimal currency values with at most two fractional digits. Invoice IDs must be unique.

Example `invoices.csv`:

```csv
invoice_id,due_date,amount
001,2026-10-14,10.00
002,2026-10-01,20.25
003,2026-08-01,30.00
004,2026-06-01,40.00
```

## Run

```sh
python aging.py invoices.csv 2026-10-13
python -m unittest discover -s . -p test_aging.py -v
```

Output is JSON with invoice count, total amount and buckets: current, 1–30, 31–60, 61–90, and 90+ days past due. Due today is current. The tool uses Python's standard library and `Decimal` for monetary amounts.

## Scope
The input is an invoice snapshot. The tool does not reconcile payments or compute interest, taxes, or exchange rates. Input validation rejects duplicate invoice IDs, negative amounts and invalid dates.
