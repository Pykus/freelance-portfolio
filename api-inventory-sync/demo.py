"""Offline end-to-end demo: start a local REST server, sync, save evidence."""
import argparse
import json
import sys
from pathlib import Path
from threading import Thread

from inventory_sync import InventoryClient, SyncError, synchronize, validate_document
from mock_api import InventoryServer


def read_items(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SyncError(f"cannot load input {path}: {type(exc).__name__}: {exc}") from exc
    return validate_document(doc)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_demo(desired_file, initial_file, output_dir):
    desired = read_items(desired_file)
    initial = read_items(initial_file)
    server = InventoryServer({"items": initial})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = InventoryClient(server.base_url, "local-demo-token")
        report = synchronize(client, desired)
        final = {"items": sorted(server.items.values(), key=lambda item: item["sku"])}
        requests_log = server.events[:]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "report.json", report)
    write_json(output / "final-state.json", final)
    write_json(output / "http-log.json", requests_log)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run offline inventory REST API sync end-to-end")
    parser.add_argument("--desired", default="examples/desired.json")
    parser.add_argument("--initial", default="examples/initial.json")
    parser.add_argument("--out-dir", default="output")
    args = parser.parse_args(argv)
    try:
        report = run_demo(args.desired, args.initial, args.out_dir)
    except (SyncError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "source_items": report["source_items"],
        "created": report["created"],
        "updated": report["updated"],
        "deleted": report["deleted"],
        "unchanged": report["unchanged"],
        "http_calls": report["http_calls"],
    }, indent=2))
    print(f"Output files: {args.out_dir}/report.json, {args.out_dir}/final-state.json, {args.out_dir}/http-log.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
