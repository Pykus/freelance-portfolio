"""Unit and CLI tests for chronological backtesting."""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import backtest, forecast_seasonal, load_demand, metrics, split_indices


def series(count=70):
    start = date(2026, 1, 1)
    return [(start + timedelta(days=i), float(8 + i % 7)) for i in range(count)]


class BacktestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.input = self.root / "demand.csv"

    def write(self, rows):
        with self.input.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "demand"])
            writer.writerows(rows)

    def audit(self, **settings):
        return backtest(series(), **{
            "train": 28, "test": 7, "gap": 2, "step": 7, "season": 7, **settings})

    def test_load_valid_series(self):
        self.write(series(5))
        self.assertEqual(len(load_demand(self.input)), 5)

    def test_reject_unsorted_dates(self):
        self.write(list(reversed(series(3))))
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            load_demand(self.input)

    def test_reject_duplicate_date(self):
        self.write([series(2)[0]] * 2)
        with self.assertRaises(ValueError):
            load_demand(self.input)

    def test_reject_nonfinite_demand(self):
        self.write([("2026-01-01", "nan")])
        with self.assertRaises(ValueError):
            load_demand(self.input)

    def test_reject_negative_demand(self):
        self.write([("2026-01-01", -2)])
        with self.assertRaises(ValueError):
            load_demand(self.input)

    def test_fold_gap(self):
        splits = list(split_indices(45, 28, 7, 2, 7))
        self.assertEqual(splits[0], (0, 28, 30, 37))
        self.assertTrue(all(b <= c for a, b, c, d in splits))

    def test_seasonal_phase_respects_gap(self):
        self.assertEqual(forecast_seasonal([1., 2., 3., 4.], 3, 2, gap=1),
                         [4., 3., 4.])

    def test_metric_arithmetic(self):
        result = metrics([2., 4.], [1., 6.])
        self.assertAlmostEqual(result["mae"], 1.5)
        self.assertAlmostEqual(result["rmse"], math.sqrt(2.5))

    def test_run_multiple_folds(self):
        result = self.audit()
        self.assertGreater(result["n_folds"], 2)
        self.assertEqual(result["n_predictions"], 7 * result["n_folds"])

    def test_all_test_dates_after_training(self):
        result = self.audit()
        self.assertTrue(all(fold["test_start"] > fold["train_end"]
                            for fold in result["folds"]))

    def test_deterministic_results(self):
        self.assertEqual(self.audit(), self.audit())

    def test_seasonal_baseline_on_weekly_pattern(self):
        result = self.audit()
        self.assertAlmostEqual(result["summary"]["seasonal"]["mae"], 0.0)

    def test_invalid_train_length(self):
        with self.assertRaises(ValueError):
            self.audit(train=1)

    def test_insufficient_history(self):
        with self.assertRaisesRegex(ValueError, "Not enough"):
            backtest(series(20), train=28, test=7, gap=2, step=7, season=7)

    def test_cli_writes_json(self):
        self.write(series())
        output = self.root / "report.json"
        subprocess.run([sys.executable, str(ROOT / "backtest.py"), str(self.input),
                        "--output", str(output)], check=True, capture_output=True)
        self.assertGreater(json.loads(output.read_text())["n_folds"], 0)


if __name__ == "__main__":
    unittest.main()
