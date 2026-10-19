# Marketplace Payout Reconciliation (Python)

## The real problem

A small online retailer sells products through a marketplace. Each month, the owner exports two reports:

- **Orders:** What customers were charged, how much was refunded, and the marketplace fee.
- **Payout transactions:** How much the marketplace says it transferred for each order.

The accountant wants to know: **Did we receive the expected net amount for every order?** Looking through hundreds of spreadsheet rows by hand is error-prone. This tool joins records by order ID, calculates exact amounts, flags discrepancies, and writes one auditable CSV.

This is a fully offline, reproducible demonstration using fictional records. It does not access real financial accounts, initiate payments, or contact any platform.

## Practical worked example

The amount expected for one order is:

~~~text
expected_net = gross - refund - fee
difference = net_paid - expected_net
~~~

Suppose **sample2** represents a fictional order with a gross amount of **USD 80.00**, a refund of **USD 10.00**, and a platform fee of **USD 4.00**.

Expected payout = 80.00 - 10.00 - 4.00 = **USD 66.00**.

The marketplace payout file reports **USD 65.90**. The software identifies a **USD -0.10 discrepancy** that the accountant should investigate. It does not guess whether the difference was caused by tax, an extra fee or a delayed adjustment.

There are six unique identifiers across the two demonstration spreadsheets:

| Order ID | Expected payout | Recorded payout | Result |
| --- | ---: | ---: | --- |
| sample1 | USD 95.00 | USD 95.00 | matched |
| sample2 | USD 66.00 | USD 65.90 | amount_mismatch |
| sample3 | EUR 48.00 | GBP 48.00 | currency_mismatch |
| sample4 | USD 24.00 | Missing | missing_payout |
| sample5 | USD 14.00 | USD 14.00 | matched |
| sample999 | No order | USD 5.00 | orphan_payout |

**Result:** Two matched transactions, one amount mismatch, one currency mismatch, one missing payout, and one payout that has no matching order. No currencies are silently converted.

## Run it

Requires Python **3.10+**, with no external dependencies. From this folder:

~~~bash
python3 generate_demo.py --output examples
python3 payout_reconcile.py \
  --orders examples/orders.csv \
  --payouts examples/payouts.csv \
  --output output
~~~

The program creates:

- **output/reconciliation.csv** — one row per unique order ID, with gross, refund, fee, expected net, actual net, difference, and review status.
- **output/summary.json** — the totals for all five statuses.

The expected summary is:

~~~json
{
  "amount_mismatch": 1,
  "currency_mismatch": 1,
  "matched": 2,
  "missing_payout": 1,
  "orphan_payout": 1,
  "total": 6
}
~~~

## Use your own input exports

Your order CSV must contain these exact column names:

~~~text
order_id,currency,gross,refund,fee
~~~

Your marketplace CSV must contain:

~~~text
order_id,currency,net_paid
~~~

Inputs must use UTF-8, unique IDs within each file, three-letter uppercase currency codes and finite monetary values exact to cents. The gross, refund and fee cannot be negative. The refund cannot exceed gross. A payout may be negative for adjustments. Repeated IDs are rejected rather than silently overwritten.

A configurable absolute tolerance (in **each row's original currency**) allows tiny rounding discrepancies:

~~~bash
python3 payout_reconcile.py \
  --orders examples/orders.csv \
  --payouts examples/payouts.csv \
  --tolerance 0.10 \
  --output review
~~~

The program retains the actual discrepancy even when its magnitude falls within the tolerance. It never performs currency conversion. All financial arithmetic uses the Python Decimal type rather than binary floating point.

## Run the tests

~~~bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q payout_reconcile.py tests
~~~

Tests cover the end-to-end CLI, exact decimal calculations, expected-versus-paid arithmetic, tolerance boundaries, unknown/missing records, duplicate IDs, missing columns, invalid values and currency mismatches, deterministic exports, and CSV formula protection.

## Engineering scope

This is a **per-order transaction reconciliation**, not a general ledger. Real marketplace payments may combine multiple orders into one payout, delay settlement for several days, apply FX conversion, collect tax or chargeback fees, or adjust previous payouts. A production integration needs source-specific rules, bank settlement matching, retries, secure credentials and an audit log.

The demonstration is intended as a transparent portfolio example for spreadsheet reconciliation work, with synthetic data and no claims of client delivery.
