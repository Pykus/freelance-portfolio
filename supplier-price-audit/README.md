# Supplier Price Change and Gross-Margin Audit

## Why a purchasing manager needs this

**Real business question:** A small retailer gets a fresh supplier price sheet each month. Which SKUs got more expensive, which disappeared, and which now leave too little gross margin at their retail selling price?

Opening two CSVs and comparing 300 product rows manually is error-prone. A simplistic text diff cannot safely handle money, newly added or discontinued products, price changes that affect margin, or a change of currency.

This offline Python tool turns **two product snapshots** into an **auditable review list**. It does not attempt to update live prices or infer exchange rates.

## Run the complete fictional example

Python **3.10+**; standard library only:

```bash
python3 price_audit.py --previous examples/before.csv --current examples/after.csv --output output
```

Open `output/price_review.csv` in Excel or LibreOffice. The program also writes `output/summary.json`.

| SKU | Change | Why a buyer should review it |
| --- | --- | --- |
| SKU-100 | Cost $10 → $12.50 | **25%** cost increase; margin falls to **16.67%** |
| SKU-200 | No change | No flags |
| SKU-300 | Removed from new list | Discontinued / missing from latest supplier feed |
| SKU-400 | Zero cost → $2 | Cannot calculate a percentage increase from a zero baseline |
| SKU-500 | USD → EUR | Currencies differ; **percentage cost change intentionally not calculated** |
| SKU-600 | New product | Listed retail price **$18** is below supplier cost **$20** |

Every SKU appears **once**, in sorted order, with old and current values and review flags. All prices and products here are synthetic.

### Business rules

- `cost_change_percent = 100 * (new cost - old cost) / old cost`, **only if currency is unchanged and old cost is above zero**.
- `gross_margin_percent = 100 * (current retail price - current unit cost) / current retail price`, unless retail price is zero.
- By default, flag a **cost increase strictly greater than 10%** and **gross margin below 20%**.
- Flag **selling below cost**, currency changes, cost increases from zero, and zero retail prices separately.
- Preserve **added**, **removed**, **changed** and **unchanged** SKUs without guessing why a record disappeared.

Customize thresholds:

```bash
python3 price_audit.py --previous examples/before.csv --current examples/after.csv --max-cost-increase 15 --min-margin 25 --output review
```

Input files require the columns `sku,currency,unit_cost,retail_price`. SKUs must be unique per snapshot; currency must be a three-letter uppercase code; money must be a finite nonnegative amount in cents. Ambiguous or invalid input fails rather than silently overwriting records. CSV cells starting with spreadsheet-formula symbols are neutralized when exported.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q price_audit.py tests
```

Tests exercise the worked example, exact decimal calculations, margin flags, zero baselines, unchanged records, threshold boundaries, invalid data, duplicate SKUs, and complete CSV/JSON export.

## What this cannot tell you

The tool does **not** convert currencies, estimate tax, freight, discounts, payment fees, or demand elasticity. It treats `retail_price` and `unit_cost` as comparable pretax per-unit amounts. Gross margin is **not** net profit. Validate supplier identifiers and use a human review before changing selling prices or purchase orders.
