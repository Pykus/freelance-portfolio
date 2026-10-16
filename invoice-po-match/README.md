# Two-Way Invoice and Purchase Order Audit

A small, dependency-free Python command-line utility that checks fictional supplier invoices against purchase orders and produces actionable review queues. It demonstrates input validation, exact money arithmetic, deterministic discrepancy codes, isolated row errors, and machine-readable CSV/JSON reporting.

This is an independent portfolio demonstration built with synthetic records, not work commissioned by or delivered to a client.

## What it checks

- Purchase order existence, supplier identity, and a three-letter currency code.
- Product identifiers (SKUs), invoiced quantities, and unit prices against a purchase order.
- Invoice line subtotals against declared subtotals, and declared subtotals plus tax against claimed totals.
- Duplicate invoice IDs within the current input batch.
- Incorrect schemas, malformed monetary values, and missing required fields.

Every invoice is classified as **READY** or **REVIEW**. Review items include stable issue codes such as PO_NOT_FOUND, SUPPLIER_MISMATCH, UNKNOWN_SKU, UNIT_PRICE_MISMATCH, QUANTITY_EXCEEDS_ORDER, SUBTOTAL_MISMATCH, TOTAL_MISMATCH, and INVALID_RECORD.

## Requirements

Python **3.10 or newer**; no packages to install. Everything uses the Python standard library. No external API, database, cloud account, or credentials are needed.

## Quick start

From inside the invoice-po-match directory:

    python invoice_po_match.py --orders examples/purchase_orders.json --invoices examples/invoices.json --output-dir output

The console prints:

    {"ready": 1, "review": 2, "total": 3}

The output directory contains:

- invoice_report.csv: one row per invoice, stable column names, semicolon-separated issue codes.
- invoice_report.json: the same detailed records plus a summary with READY and REVIEW counts.

For the included example, invoice INV-100 is READY; INV-101 must be reviewed for excessive quantity and wrong subtotal; INV-102 has a supplier mismatch. No example contains private or customer information.

## Data format

Both inputs are **JSON arrays**. Example purchase order entry:

    {
      "po_id": "PO-100",
      "supplier": "Fictional Components Ltd",
      "currency": "USD",
      "items": [{"sku": "RES-10K", "quantity": 4, "unit_price": "12.50"}]
    }

Example invoice entry:

    {
      "invoice_id": "INV-100",
      "po_id": "PO-100",
      "supplier": "Fictional Components Ltd",
      "currency": "USD",
      "items": [{"sku": "RES-10K", "quantity": 2, "unit_price": "12.50"}],
      "claimed_subtotal": "25.00",
      "tax": "2.00",
      "claimed_total": "27.00"
    }

Money fields must be **strings with at most two decimal places** (for example "0", "2.50", or "19.9"). They are converted to integer cents; floating-point money inputs are rejected rather than rounded. Quantities are positive integers, and item SKUs must be unique within each document.

## How the arithmetic works

For an item with quantity 2 and unit price $12.50, the line subtotal is 2 x 1,250 cents = 2,500 cents, or $25.00. If the invoice reports $24.00, the auditor emits SUBTOTAL_MISMATCH. Separately, if the declared subtotal is $25.00 and tax is $2.00, the declared total must be $27.00. Both checks are independent so errors can be investigated precisely.

## Tests

Run from the project directory:

    python -m unittest discover -s tests -p "test_*.py" -v
    python -m compileall -q invoice_po_match.py tests

The suite covers valid matching, malformed prices, duplicate IDs and SKUs, boolean quantities, missing purchase orders, supplier/currency discrepancies, unknown products, price and quantity mismatches, incorrect totals, invalid records, CLI error handling, and end-to-end CSV/JSON generation.

## Limitations

This is a deterministic **two-way** checker, not a full accounts-payable system. It does not read PDFs or perform OCR, integrate with ERP/payment systems, calculate taxes or foreign-exchange conversions, track cumulative partial invoicing against a PO, cross-check goods receipts, or approve payments. READY means that only the explicitly documented checks passed, **not** that an invoice should be paid. Treat the outputs as a starting point for human review.
