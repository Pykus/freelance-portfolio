# CSV Data Cleaner

A small, dependency-free Python CLI for cleaning business CSV exports. Uses fictional customer records.

## Business problem

A company exports customer records with inconsistent whitespace, duplicate email addresses, and incomplete rows. This utility produces a cleaned CSV and a machine-readable processing summary.

## Features

- Trim whitespace from headers and values
- Skip completely blank records
- Filter rows missing specified required columns
- Deduplicate by one or more selected columns (case-insensitive)
- Preserve leading zeros by treating CSV values as strings
- Reject unknown columns, duplicate normalized headers, and malformed extra fields
- Use only the Python standard library; no credentials or network access

## End-to-end example: input -> processing -> output

**The tool changes the data and writes a new CSV file.** The JSON shown in the terminal is only a processing summary, not the result file.

### 1. Input file

The repository includes [`examples/customers.csv`](examples/customers.csv), with **six data rows** (plus the header). This is the complete input, including whitespace in rows 001 and 002:

```csv
customer_id,name,email,city
001, Alice Smith ,alice@example.com, London
002,Bob Jones,bob@example.com,Berlin
003,ALICE SMITH,ALICE@example.com,London
004,Charlie Brown,,Warsaw
,,,
005,Dana Lee,dana@example.com,Gdansk
```

### 2. Run the transformation

Requires Python 3.9+. From the repository root:

```bash
cd csv-data-cleaner
python cleaner.py examples/customers.csv output/customers-clean.csv --required email --dedupe-by email
```

The command reads `examples/customers.csv`, requires a nonempty `email` value, and uses the case-insensitive email address as the duplicate key. The first occurrence wins.

### 3. Actual output file

The command creates `output/` if needed and writes **`output/customers-clean.csv`**. This is the complete generated file, containing **three data rows**:

```csv
customer_id,name,email,city
001,Alice Smith,alice@example.com,London
002,Bob Jones,bob@example.com,Berlin
005,Dana Lee,dana@example.com,Gdansk
```

What happened to each input row:

| Input row | Result | Reason |
| --- | --- | --- |
| 001 | Kept, cleaned | Trimmed spaces around name and city |
| 002 | Kept | Already valid |
| 003 | Removed | Email duplicates row 001 (case-insensitive) |
| 004 | Removed | Required `email` is empty |
| Entirely empty row | Removed | All fields are empty |
| 005 | Kept | Valid unique email |

The **original input file is not modified** when using the separate paths above. If the output path already exists, the program **overwrites that output file**. Do not pass the same path as input and output if you want to retain the original.

Inspect the generated CSV:

```bash
# macOS / Linux
cat output/customers-clean.csv
```

```powershell
# Windows PowerShell
Get-Content output/customers-clean.csv
```

You can also open the generated CSV in Excel.

### 4. Console summary (not the output file)

The command also prints these counts:

```json
{
  "read": 6,
  "written": 3,
  "blank": 1,
  "missing_required": 1,
  "duplicates": 1
}
```

These counts match the six input rows and three retained output rows shown above.

## Test

```bash
cd csv-data-cleaner
python -m unittest discover -s tests -v
```

## Design decisions and limitations

- All values remain text to avoid damaging IDs such as `001`.
- The first occurrence of a duplicate is retained.
- Deduplication ignores letter case but does not normalize phone numbers, Unicode, or email aliases.
- The entire output is held in memory; for very large files, use a streaming or database-based solution.
- Input files are read completely before the destination is opened, reducing the risk of accidental truncation. Always use a separate destination to preserve the original source; an existing destination is overwritten.
- CSV data is not sanitized for spreadsheet formula injection; review untrusted data before opening in spreadsheet software.
- No personal data is included in this repository.
