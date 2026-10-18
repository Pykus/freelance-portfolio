"""Chronological walk-forward backtesting with explicit gaps and simple baselines."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path


def load_demand(path: Path) -> list[tuple[date, float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != ["date", "demand"]:
            raise ValueError("Expected columns: date,demand")
        observations = []
        for line, row in enumerate(reader, start=2):
            if None in row or row["date"] is None or row["demand"] is None:
                raise ValueError(f"Malformed row {line}")
            try:
                day = date.fromisoformat(row["date"])
                value = float(row["demand"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid observation at row {line}") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Non-finite or negative demand at row {line}")
            if observations and day <= observations[-1][0]:
                raise ValueError(f"Dates must be strictly increasing at row {line}")
            observations.append((day, value))
    if not observations:
        raise ValueError("Demand series is empty")
    return observations


def split_indices(total: int, train: int, test: int, gap: int, step: int):
    if train < 2 or test < 1 or gap < 0 or step < 1:
        raise ValueError("Invalid fold dimensions")
    for start in range(0, total - (train + gap + test) + 1, step):
        yield start, start + train, start + train + gap, start + train + gap + test


def forecast_last(training: list[float], count: int) -> list[float]:
    if not training:
        raise ValueError("Training data required")
    return [training[-1]] * count


def forecast_seasonal(training: list[float], count: int, season: int, gap: int = 0) -> list[float]:
    if season < 1 or season > len(training):
        raise ValueError("Season must fit training window")
    previous_season = training[-season:]
    return [previous_season[(gap + index) % season] for index in range(count)]


def metrics(actual: list[float], prediction: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(prediction):
        raise ValueError("Both vectors must have equal, positive length")
    errors = [a - b for a, b in zip(actual, prediction)]
    return {
        "mae": math.fsum(abs(e) for e in errors) / len(errors),
        "rmse": math.sqrt(math.fsum(e * e for e in errors) / len(errors)),
    }


def backtest(rows: list[tuple[date, float]], *,
             train: int, test: int, gap: int, step: int, season: int) -> dict:
    if season < 1 or season > train:
        raise ValueError("Season must fit the training window")
    values = [value for _, value in rows]
    folds = []
    observed: list[float] = []
    last_pred: list[float] = []
    seasonal_pred: list[float] = []
    for begin, train_end, test_begin, test_end in split_indices(
            len(rows), train, test, gap, step):
        history = values[begin:train_end]
        truth = values[test_begin:test_end]
        previous = forecast_last(history, len(truth))
        cyclical = forecast_seasonal(history, len(truth), season, gap=gap)
        observed.extend(truth)
        last_pred.extend(previous)
        seasonal_pred.extend(cyclical)
        folds.append({
            "train_start": rows[begin][0].isoformat(),
            "train_end": rows[train_end - 1][0].isoformat(),
            "test_start": rows[test_begin][0].isoformat(),
            "test_end": rows[test_end - 1][0].isoformat(),
            "n_train": len(history),
            "n_test": len(truth),
            "last_value": metrics(truth, previous),
            "seasonal": metrics(truth, cyclical),
        })
    if not folds:
        raise ValueError("Not enough observations to form one fold")
    return {
        "parameters": {
            "train": train, "test": test, "gap": gap,
            "step": step, "season": season,
        },
        "n_folds": len(folds),
        "n_predictions": len(observed),
        "summary": {
            "last_value": metrics(observed, last_pred),
            "seasonal": metrics(observed, seasonal_pred),
        },
        "folds": folds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--train", type=int, default=28)
    parser.add_argument("--test", type=int, default=7)
    parser.add_argument("--gap", type=int, default=2)
    parser.add_argument("--step", type=int, default=7)
    parser.add_argument("--season", type=int, default=7)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = backtest(
            load_demand(args.csv_file), train=args.train, test=args.test,
            gap=args.gap, step=args.step, season=args.season,
        )
        serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Backtest failed: {exc}\n")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
