# Freelance Automation Portfolio

Practical, small-scale software demonstrations inspired by common freelance tasks. Projects use synthetic or openly licensed data and do not contain client code or confidential information.

## Projects

| Project | What it demonstrates | Stack |
| --- | --- | --- |
| [CSV Data Cleaner](csv-data-cleaner/) | Cleaning, validation, deduplication and tests for business CSV exports | Python standard library |
| [JSON Orders → SQLite ETL](json-sqlite-etl/) | Validate fictional JSON orders, load real SQLite records, generate an audit report and run 8 tests | Python standard library, SQLite |
| [Inventory REST API Synchronizer](api-inventory-sync/) | Synchronize fictional stock through a local REST API; audit HTTP calls and final inventory with 14 tests | Python standard library, HTTP |
| [HTML Catalog Change Tracker](web-snapshot-diff/) | Parse fictional HTML snapshots, preserve SQLite history and report additions, updates and removals with 16 tests | Python standard library, SQLite |
| [CSV Export Reconciliation](csv-reconciliation/) | Compare two CSV exports by stable ID and report added, removed and changed records | Python standard library |

| [CSV Schema Validator](csv-schema-validator/) | Validate CSV exports against a JSON schema and report row-level errors | Python standard library |

| [JSON Configuration Diff](json-config-diff/) | Compare nested JSON snapshots and report additions, removals and changes | Python standard library |

| [Image Asset Quality Audit](image-asset-audit/) | Detect corrupted images, undersized files and exact duplicates, exporting CSV/JSON reports with tests | Python, Pillow |

| [Offline Email Order Intake](email-order-intake/) | Parse and validate fictional order emails with SQLite deduplication, exact monetary totals and CSV audit reports | Python standard library, SQLite |

| [Website Provider Research Shortlist](footprint-search-batch/) | Generate PublicWWW queries, import copied results, deduplicate by website domain, retain every matching clue, and export a practical CSV shortlist with 23 tests | Python standard library |
| [Invoice to Purchase Order Audit](invoice-po-match/) | Match synthetic invoices to purchase orders, flag discrepancies, and export review reports with regression tests | Python standard library |
| [Website Redirect Map Audit](redirect-map-audit/) | Check website migration plans for missing redirects, chains, loops and conflicting rules; export a review list with 16 tests | Python standard library |
| [Helpdesk First-Response SLA Audit](support-ticket-sla/) | Check ticket response deadlines across timezones, flag overdue and missing responses, and export reports with 20 tests | Python standard library |

| [Backup Manifest Integrity Checker](backup-manifest-integrity/) | Create and verify portable SHA-256 inventories of offline file deliveries, with documented change reports and regression tests | Python standard library |

| [Walk-Forward Demand Forecast Backtest](time-series-backtest-audit/) | Compare leakage-aware chronological folds, naive and seasonal baselines, and per-fold forecast errors | Python standard library |

Each project includes setup instructions, sample inputs, test commands and limitations.
