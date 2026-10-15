# Local Image Asset Quality Audit

A practical Python command-line utility for auditing a batch of locally stored PNG
and JPEG assets **without downloading anything**. It produces a machine-readable CSV
inventory and a JSON summary. Input and example data are entirely synthetic.

The tool solves a common production subtask: before a set of images is handed to a
catalog, publishing workflow or image-processing pipeline, identify files that are
unreadable, smaller than the required dimensions, or exact-byte duplicates.

## What it does

- Traverses nested folders in a stable, alphabetical order.
- Reads and fully decodes PNG/JPEG files with Pillow, detecting many corrupt files.
- Records file size, SHA-256, detected image format, and pixel dimensions.
- Detects **exact-byte** duplicates and identifies the first matching relative filename.
- Enforces configurable minimum width **and** height.
- Produces CSV detail and JSON detail/summary, using atomic replacement for each file.
- Refuses to follow symbolic links and optionally exits with code `2` for invalid images.
- Uses only local files. There are no accounts, credentials, network requests or APIs.

## Setup

Requires Python 3.10+ and Pillow; a virtual environment is recommended.

```bash
python -m venv .venv
# Activate the environment using your operating system's usual command.
python -m pip install -r requirements.txt
python examples/generate_samples.py sample-images
python audit.py sample-images --min-width 400 --min-height 300 \
    --csv output/audit.csv --json output/audit.json
```

For the generated sample data the summary is:

```json
{"duplicate": 1, "invalid": 1, "too_small": 1, "total": 4, "valid": 1}
```

`output/audit.csv` contains one row per PNG/JPEG candidate with columns `path`,
`bytes`, `sha256`, `format`, `width`, `height`, `status` and `reason`. `output/audit.json`
contains the same records plus the summary and the applied minimum dimensions.
Only **relative** source filenames appear in reports; input directories are not exposed.

## Command-line reference

```bash
python audit.py INPUT_DIRECTORY --csv REPORT.csv --json REPORT.json \
    [--min-width 400] [--min-height 300] [--fail-on-invalid]
```

Both output paths must be different. The defaults are 400×300 pixels. Invalid
arguments or inaccessible directories cause a nonzero exit. Without
`--fail-on-invalid`, the program reports invalid files and exits with zero after
writing both reports, which is useful for exploratory audits. With the flag, it
writes the reports first and exits with `2` if any file is invalid.

Status meaning:

| Status | Meaning |
| --- | --- |
| `valid` | File is decodable, large enough and the first with those exact bytes. |
| `duplicate` | SHA-256 matches an earlier decoded file, regardless of dimensions. |
| `too_small` | At least one pixel dimension is below the configured minimum. |
| `invalid` | Image cannot be decoded, contains an unexpected format, or is a symbolic link. |

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests create all image fixtures dynamically in temporary directories, exercise
both PNG and JPEG, corrupted images, dimension boundaries, deduplication,
report serialization, paths, CLI exit codes and symlink handling. No external
services or original client material are needed.

## Limits and extensions

- Only `.png`, `.jpg` and `.jpeg` files are inspected. Other extensions are ignored.
- Dimensions are stored pixel dimensions, not EXIF-oriented display dimensions.
- SHA-256 finds identical **files**, not visually similar images or copies that
  have been recompressed or resized.
- Successful decoding cannot guarantee aesthetic quality or provenance. The
  tool does not assess copyright, subject matter, color accuracy or licensing.
- Very large images trigger Pillow's decompression-bomb protection.
- The two reports are written atomically **individually**, not as one transaction.
- It does not scrape or retrieve images. A production acquisition component
  would need separate source permissions, rate limiting, attribution and logging.

This is an independent demonstration of a reusable image-quality workflow,
not a commissioned delivery or a reproduction of any customer's dataset.
