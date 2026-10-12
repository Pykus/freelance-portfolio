import unittest
from inventory_sync import SyncError, validate_document


class ValidationTests(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(validate_document({'items': []}), [])

    def sample(self, **edits):
        row = {"sku": "SKU-AAA", "price_cents": 200, "quantity": 3}
        row.update(edits)
        return row

    def test_normalizes_sku_order(self):
        rows = validate_document({"items": [
            self.sample(sku="SKU-ZZZ"),
            self.sample(sku="SKU-AAA")]})
        self.assertEqual([row["sku"] for row in rows], ["SKU-AAA", "SKU-ZZZ"])

    def test_duplicate_sku_rejected(self):
        with self.assertRaisesRegex(SyncError, "duplicate"):
            validate_document({"items": [self.sample(), self.sample()]})

    def test_nonpositive_and_fractional_prices_rejected(self):
        for value in (-1, 0, True, 1.5, "1.25"):
            with self.subTest(price=value), self.assertRaises(SyncError):
                validate_document({"items": [self.sample(price_cents=value)]})

    def test_invalid_quantities_rejected(self):
        for value in (-1, True, 1.5, "2"):
            with self.subTest(quantity=value), self.assertRaises(SyncError):
                validate_document({"items": [self.sample(quantity=value)]})

    def test_invalid_skus_rejected(self):
        for value in ("abc", "SKU 1", "../abc", "", None):
            with self.subTest(sku=value), self.assertRaises(SyncError):
                validate_document({"items": [self.sample(sku=value)]})

    def test_invalid_json_structure_rejected(self):
        for doc in ([], {}, {"items": {}}, {"items": [1]},
                    {"items": [dict(self.sample(), unexpected="extra")]}):
            with self.subTest(doc=doc), self.assertRaises(SyncError):
                validate_document(doc)

    def test_missing_token_rejected(self):
        from inventory_sync import InventoryClient
        with self.assertRaisesRegex(SyncError, "token"):
            InventoryClient("http://127.0.0.1:80", "")

    def test_wrong_http_base_rejected(self):
        from inventory_sync import InventoryClient
        with self.assertRaises(SyncError):
            InventoryClient("not-a-url", "fake-token")

[executed on device: PP-HP-Touch (b2eaef45-2c98-4bb8-b494-8af5760909a9)]
