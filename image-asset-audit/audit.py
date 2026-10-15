"""Audit local PNG/JPEG image assets without accessing the network."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, TextIO

from PIL import Image, UnidentifiedImageError

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_FORMATS = {"JPEG", "PNG"}
FIELDNAMES = ["path", "bytes", "sha256", "format", "width", "height", "status", "reason"]


@dataclass(frozen=True)
class AssetRecord:
    path: str
    bytes: int | None
    sha256: str | None
    format: str | None
    width: int | None
    height: int | None
    status: str
    reason: str


def file_digest(path: Path) -> str:
    """Hash bytes in bounded chunks, not by reading the entire file at once."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path: Path) -> tuple[str, int, int]:
    """Check the decoder can read all pixels; report stored pixel dimensions."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            image_format = image.format
            if image_format not in SUPPORTED_FORMATS:
                raise ValueError("File contents are not PNG or JPEG")
            image.verify()
        with Image.open(path) as image:
            image.load()  # Decode the full image, not just its header.
            width, height = image.size
            return image_format, width, height


def audit_directory(directory: Path, min_width: int, min_height: int) -> dict:
    """Return deterministic records; an exact-byte duplicate keeps its first filename."""
    if min_width < 1 or min_height < 1:
        raise ValueError("Minimum dimensions must be positive integers")
    if not directory.is_dir():
        raise ValueError("Input must be an existing directory")

    seen_hashes: dict[str, str] = {}
    records: list[AssetRecord] = []
    candidates = sorted(
        (p for p in directory.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda p: p.relative_to(directory).as_posix(),
    )
    for path in candidates:
        relative_name = path.relative_to(directory).as_posix()
        if path.is_symlink():
            records.append(AssetRecord(relative_name, None, None, None, None, None,
                                       "invalid", "Symbolic links are not processed"))
            continue
        if not path.is_file():
            records.append(AssetRecord(relative_name, None, None, None, None, None,
                                       "invalid", "Not a regular file"))
            continue
        byte_count: int | None = None
        sha: str | None = None
        try:
            byte_count = path.stat().st_size
            sha = file_digest(path)
            image_format, width, height = inspect_image(path)
            expected_format = "PNG" if path.suffix.lower() == ".png" else "JPEG"
            if image_format != expected_format:
                raise ValueError("Filename extension does not match image format")
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as exc:
            records.append(AssetRecord(relative_name, byte_count, sha, None, None, None,
                                       "invalid", f"Cannot decode image: {type(exc).__name__}"))
            continue

        if sha in seen_hashes:
            status, reason = "duplicate", f"Exact duplicate of {seen_hashes[sha]}"
        elif width < min_width or height < min_height:
            status, reason = "too_small", f"Below {min_width}x{min_height} pixel minimum"
        else:
            status, reason = "valid", ""
        seen_hashes.setdefault(sha, relative_name)
        records.append(AssetRecord(relative_name, byte_count, sha, image_format,
                                   width, height, status, reason))

    counts = {name: sum(r.status == name for r in records)
              for name in ("valid", "duplicate", "too_small", "invalid")}
    return {"summary": {"total": len(records), **counts},
            "minimum_dimensions": {"width": min_width, "height": min_height},
            "records": [asdict(r) for r in records]}


def _write_atomically(destination: Path, populate: Callable[[TextIO], None]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=destination.parent, prefix=".audit-",
                                         delete=False) as output:
            tmp_path = Path(output.name)
            populate(output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp_path, destination)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def write_reports(result: dict, csv_path: Path, json_path: Path) -> None:
    if csv_path.resolve() == json_path.resolve():
        raise ValueError("CSV and JSON output paths must be different")

    def write_csv(output: TextIO) -> None:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(result["records"])

    def write_json(output: TextIO) -> None:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")

    _write_atomically(csv_path, write_csv)
    _write_atomically(json_path, write_json)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Local image directory")
    parser.add_argument("--min-width", type=int, default=400)
    parser.add_argument("--min-height", type=int, default=300)
    parser.add_argument("--csv", type=Path, required=True, help="Destination CSV report")
    parser.add_argument("--json", type=Path, required=True, help="Destination JSON report")
    parser.add_argument("--fail-on-invalid", action="store_true",
                        help="Exit with status 2 if any image is invalid")
    args = parser.parse_args(argv)
    try:
        result = audit_directory(args.directory, args.min_width, args.min_height)
        write_reports(result, args.csv, args.json)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 2 if args.fail_on_invalid and result["summary"]["invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
