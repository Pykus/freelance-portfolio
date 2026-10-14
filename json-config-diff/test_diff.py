import unittest
from diff import compare

class ConfigDiffTests(unittest.TestCase):
    def test_added_removed_changed(self):
        result = compare({"a": 1, "b": {"x": 2}, "gone": True},
                         {"a": 1, "b": {"x": 3}, "new": 4})
        self.assertEqual(result["added"], {"/new": 4})
        self.assertEqual(result["removed"], {"/gone": True})
        self.assertEqual(result["changed"], {"/b/x": {"before": 2, "after": 3}})
    def test_boolean_differs_from_integer(self):
        self.assertIn("/a", compare({"a": True}, {"a": 1})["changed"])
    def test_list_indices(self):
        self.assertIn("/items/1", compare({"items": [1,2]}, {"items": [1,3]})["changed"])
    def test_escaping(self):
        self.assertIn("/a~1b", compare({}, {"a/b": 1})["added"])

if __name__ == "__main__":
    unittest.main()
