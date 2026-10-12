"""Integration tests execute actual loopback HTTP requests; no external network."""
import json
import tempfile
import unittest
from pathlib import Path
from threading import Thread

from demo import main, read_items, run_demo
from inventory_sync import InventoryClient, SyncError, synchronize
from mock_api import InventoryServer

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "out"
        self.initial = ROOT / "examples/initial.json"
        self.desired = ROOT / "examples/desired.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_end_to_end_matches_all_three_committed_fixtures(self):
        report = run_demo(self.desired, self.initial, self.output)
        for name in ("report.json", "final-state.json", "http-log.json"):
            expected = json.loads((ROOT / "examples" / ("expected-" + name)).read_text(encoding="utf-8"))
            actual = json.loads((self.output / name).read_text(encoding="utf-8"))
            self.assertEqual(actual, expected, name)
            if name == "report.json":
                self.assertEqual(report, expected)
        self.assertEqual(report["http_calls"], 5)

    def test_running_cli_creates_three_real_files(self):
        self.assertEqual(main(["--desired", str(self.desired), "--initial", str(self.initial),
                               "--out-dir", str(self.output)]), 0)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),
                         ["final-state.json", "http-log.json", "report.json"])

    def test_second_reconciliation_is_no_op(self):
        server = InventoryServer({"items": read_items(self.initial)})
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            first = synchronize(InventoryClient(server.base_url, "local-demo-token"), read_items(self.desired))
            second = synchronize(InventoryClient(server.base_url, "local-demo-token"), read_items(self.desired))
            self.assertEqual((first["created"], first["updated"], first["deleted"]),
                             (["SKU-300"], ["SKU-200"], ["SKU-OLD"]))
            self.assertEqual(second["created"], [])
            self.assertEqual(second["updated"], [])
            self.assertEqual(second["deleted"], [])
            self.assertEqual(second["unchanged"], ["SKU-100", "SKU-200", "SKU-300"])
            self.assertEqual(second["http_methods"], {"GET": 2, "POST": 0, "PUT": 0, "DELETE": 0})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_conflicting_post_raises_http_error_and_keeps_original(self):
        server = InventoryServer({"items": read_items(self.initial)})
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = InventoryClient(server.base_url, "local-demo-token")
            with self.assertRaisesRegex(SyncError, "HTTP 409"):
                client.send("POST", "/items", {"sku": "SKU-100", "price_cents": 2, "quantity": 3})
            self.assertEqual(server.items["SKU-100"]["price_cents"], 1250)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_invalid_document_exits_before_creating_outputs(self):
        source = Path(self.tmp.name) / "invalid.json"
        source.write_text('{"items": "not a list"}', encoding="utf-8")
        self.assertEqual(main(["--desired", str(source), "--initial", str(self.initial),
                               "--out-dir", str(self.output)]), 1)
        self.assertFalse(self.output.exists())
