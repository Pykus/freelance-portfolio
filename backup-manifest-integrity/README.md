# Backup Manifest Integrity Checker

A reproducible, offline Python utility that builds a SHA-256 checksum inventory of a directory and later checks for missing, changed, or unexpected files. This is useful when copying website assets, delivering batches of exported reports, or validating that a backup directory was transferred without silent corruption.

## What it detects

The tool records each regular file's relative POSIX path, byte length, and SHA-256 digest. Verification compares both file size and digest. It reports four outcomes: unchanged files, changed files, missing files, and new unexpected files. Path traversal and invalid checksums in a manifest are rejected rather than trusted.

## Requirements

Python 3.11 or newer. All code uses the standard library; no account, network connection, API credential, or database is required.

## Example

Create a directory of invented test files:

    mkdir -p sample
    printf 'First synthetic record\n' > sample/alpha.txt
    printf 'Second synthetic record\n' > sample/beta.txt

Build the manifest and inspect it:

    python3 backup_manifest.py build sample sample-manifest.json

Check the directory against the saved manifest:

    python3 backup_manifest.py check sample sample-manifest.json

Edit alpha.txt and repeat the second command to see the changed file identified. A clean check exits with status 0; detected differences return status 1; malformed input or an I/O problem returns status 2.

If the output manifest is placed inside the directory being inventoried, the tool excludes that file from its own file listing.

## Example output

    {
      "changed": ["alpha.txt"],
      "checked": 2,
      "missing": [],
      "ok": false,
      "unexpected": []
    }

## Testing

    python3 -m unittest discover -s tests -v
    python3 -m py_compile backup_manifest.py tests/test_backup_manifest.py

The automated tests cover deterministic inventories, nested paths, edits, missing files, unexpected files, path validation, bad checksums, and command-line behavior.

## Implementation notes

Files are read in 1 MiB chunks to avoid loading an entire large file into memory. Entries are sorted by relative path for stable, reviewable output. The JSON manifest records a format version and checksum algorithm so incompatible inputs are rejected clearly.

Symbolic links are rejected rather than followed. This avoids silently reading locations outside the selected directory. A completed scan describes files at the times they were read; if files are modified concurrently, the resulting manifest is not a filesystem snapshot.

## Project files

- backup_manifest.py: inventory, checksum, validation, report, and CLI.
- tests/test_backup_manifest.py: repeatable regression and integration checks.

## Limits and next steps

SHA-256 verifies file content against a saved digest, not who created or approved that digest. Store a trusted copy of a manifest separately from the backup. A production workflow could add signed manifests, a retry mechanism for changing files, and scheduled comparison reports.
