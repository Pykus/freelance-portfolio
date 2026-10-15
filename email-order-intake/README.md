# Offline Email Order Intake

A small, fully local Python program that reads RFC 822 email files, validates fictional orders, stores accepted records in SQLite, and produces an auditable CSV report. The input directory stands in for an email inbox: no mail account, API key, network service, or external database is required.

## Problem and approach

Repeatedly exporting email orders can create duplicate records and subtle accounting errors. This demo separates validation from persistence and makes repeats safe by checking both the email Message-ID and business Order-ID. Amounts use integer cents rather than floating-point arithmetic. Invalid messages are listed in the CSV report instead of silently discarded.

The program demonstrates a deterministic portion of an email-ingestion pipeline, not production IMAP, PDF extraction, AI parsing, or MySQL integration.

## Requirements

Python 3.10+; only the standard library is used. From the project directory, run:

    python3 order_intake.py --input examples/inbox --db output/orders.sqlite3 --report output/report.csv

Expected console summary on a fresh database:

    {"duplicate": 0, "imported": 1, "rejected": 1}

Running the command again with the same database demonstrates idempotency:

    {"duplicate": 1, "imported": 0, "rejected": 1}

The first input is stored; the second is rejected because it contains an invalid negative quantity. The generated CSV can be compared to the checked-in examples/expected-report.csv after the first run. Generated output and SQLite files should stay outside the source tree or in a directory ignored by Git.

## Input contract

Place one or more .eml files in the input folder (non-recursive). Each email must have a valid Message-ID, sender address and a subject beginning with Order. Only the text/plain body is parsed. The following fields are required:

    Order-ID: SO-4101
    Customer: Fictional Office Supply
    Item: NOTEBOOK-A5, 2, 6.75
    Item: PEN-BLACK, 4, 1.20

Order-ID must have the form SO- followed by 4–8 digits. Every Item contains an uppercase alphanumeric SKU, a whole-number quantity from 1 to 10000, and a nonnegative price with exactly two decimal places. At least one Item is required. Unsupported fields and invalid messages are rejected; messages above 1 MB are not loaded.

## Output contract

The SQLite database has orders and order_lines tables. A successful order and its items are inserted in one transaction. The report contains source_file, status, order_id, total, and details. Possible statuses are imported, duplicate and rejected. The report is replaced atomically only after it has been fully written. Every execution prints the status counts as JSON.

Example: 2 notebooks at 6.75 and 4 pens at 1.20 produce 2 x 6.75 + 4 x 1.20 = 18.30 (1830 cents). The sample report contains this amount.

## Tests

Run from this directory:

    python3 -m unittest discover -s tests -v
    python3 -m py_compile order_intake.py

Tests cover integer-cent arithmetic, transaction persistence, repeated runs, conflicting order identifiers, MIME bodies, malformed and missing fields, HTML-only input, email size limits, failure isolation and command-line operation.

## Scope and limitations

This is an independent portfolio demonstration using synthetic messages and fictional identities, not a client deliverable. It does not connect to or poll a real email account. It does not parse PDF attachments or guarantee business-schema compatibility with any external platform. For production, add authenticated inbox access, concurrency-safe delivery guarantees, malware scanning, privacy controls, operational monitoring and versioned schemas.
