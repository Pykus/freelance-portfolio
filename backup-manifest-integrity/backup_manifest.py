"""Build and verify portable SHA-256 manifests for local backup folders."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FORMAT_VERSION = 1


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, *, exclude: Path | None = None) -> dict[str, dict]:
    if not root.is_dir():
        raise ValueError("Root must be an existing directory")
    root = root.resolve()
    ignored = exclude.resolve() if exclude else None
    items: dict[str, dict] = {}
    for file in root.rglob("*"):
        if file.is_symlink():
            raise ValueError(f"Symbolic link is not supported: {file.relative_to(root)}")
        if not file.is_file() or (ignored and file.resolve() == ignored):
            continue
        relative = file.relative_to(root).as_posix()
        items[relative] = {"size": file.stat().st_size, "sha256": file_hash(file)}
    return dict(sorted(items.items()))


def build(root: Path, output: Path) -> dict:
    if not output.parent.exists():
        output.parent.mkdir(parents=True)
    manifest = {
        "version": FORMAT_VERSION,
        "algorithm": "sha256",
        "files": inventory(root, exclude=output),
    }
    serialized = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temp = output.with_name(output.name + ".tmp")
    if temp.exists():
        raise ValueError("Temporary output path already exists")
    try:
        temp.write_text(serialized, encoding="utf-8")
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    return manifest


def validate(manifest: object) -> dict[str, dict]:
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must contain a JSON object")
    if manifest.get("version") != FORMAT_VERSION or manifest.get("algorithm") != "sha256":
        raise ValueError("Unsupported manifest format or checksum algorithm")
    entries = manifest.get("files")
    if not isinstance(entries, dict):
        raise ValueError("Manifest files must be a mapping")
    for relative, item in entries.items():
        if not isinstance(relative, str) or not relative:
            raise ValueError("Every file needs a nonempty path")
        name = PurePosixPath(relative)
        if (name.is_absolute() or relative.startswith("./") or
                "\\" in relative or any(piece in ("", ".", "..") for piece in relative.split("/"))):
            raise ValueError(f"Unsafe manifest path: {relative}")
        if not isinstance(item, dict):
            raise ValueError("Each file entry must be an object")
        size, checksum = item.get("size"), item.get("sha256")
        if type(size) is not int or size < 0 or not isinstance(checksum, str) or not SHA256.fullmatch(checksum):
            raise ValueError(f"Invalid file metadata: {relative}")
    return entries


def check(root: Path, manifest_path: Path) -> dict:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = validate(document)
    actual = inventory(root, exclude=manifest_path)
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    changed = sorted(
        name for name in expected.keys() & actual.keys()
        if expected[name] != actual[name]
    )
    return {
        "ok": not (missing or unexpected or changed),
        "checked": len(expected),
        "missing": missing,
        "changed": changed,
        "unexpected": unexpected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    make = actions.add_parser("build", help="Record sizes and SHA-256 checksums")
    make.add_argument("root", type=Path)
    make.add_argument("output", type=Path)
    verify = actions.add_parser("check", help="Compare folder to saved manifest")
    verify.add_argument("root", type=Path)
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            result = build(args.root, args.output)
        else:
            result = check(args.root, args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Audit failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if args.action == "build" or result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
