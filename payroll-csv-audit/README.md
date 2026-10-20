# Payroll CSV Quality Auditor

An offline Python utility for reviewing monthly payroll exports before importing them into accounting tools. It identifies suspicious records without modifying original data. All regression fixtures are synthetic.

## Features

- Validate required headers, numeric fields, missing IDs or stores and malformed rows.
- Flag every occurrence of duplicate employee IDs, including the first.
- Identify high overtime, overtime exceeding worked hours and implausibly large hour totals.
- Use exact decimal numbers; reject negatives, NaN and infinity.
- Export source row values and issue codes to CSV, plus aggregate counts to JSON.
- Mitigate spreadsheet formula injection when exporting issues.
- Use atomic file replacement for each report.
- Require only Python 3.11+ and the standard library.

## Run

From this directory, run:

    python3 -m payroll_review examples/template.csv --issues issues.csv --summary summary.json
    python3 -m unittest discover -s tests -v

The starter template contains headers only, so its first report has zero input rows. Populate a copy with your own records to review data; tests exercise synthetic valid, invalid and duplicate records.

To change the review threshold:

    python3 -m payroll_review examples/template.csv --issues issues.csv --summary summary.json --max-overtime 15

## Input schema

Required fields: employee_id, store, contracted_hours, worked_hours, overtime_hours, sick_hours, vacation_hours, hourly_rate, bonus.

Extra columns are preserved. UTF-8 with or without BOM is supported. Identifiers are compared after trimming and case folding. The issues CSV adds row_number and semicolon-separated issue_codes.

## Limitations

This is a data-quality review, not a payroll engine or a legal compliance checker. It does not calculate wages, taxes or benefits. Thresholds are examples, not employment-law rules. Input rows are held in memory for duplicate detection. Reports are replaced independently, not as a multi-file transaction.

See DESIGN.md for validation decisions and safeguards.
