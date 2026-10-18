# Walk-Forward Demand Forecast Backtest

An offline, reproducible Python program that compares two simple forecasting baselines without mixing future observations into their training windows. It produces one JSON report with fold boundaries, per-fold errors and aggregate metrics.

## Why chronological splitting matters

Random train/test splits are often inappropriate for time series: observations that happened later can influence what should have been a past prediction. This tool uses fixed-length rolling training windows, a configurable gap between training and testing, and chronological test windows. Forecasts are generated solely from training observations.

## Baselines

**Last value:** predicts every day of the test horizon using the final demand observation in the training window.

**Seasonal repeat:** repeats values from the latest training season (seven observations by default). The season is aligned to the test horizon, including skipped observations in the gap.

Neither baseline re-fits itself on test labels. Both use only the Python standard library.

## Run with example data

Python 3.11+ is required. From this project directory run:

    python3 backtest.py examples/daily_demand.csv --train 28 --test 7 --gap 2 --step 7 --season 7 --output report.json

The report contains the dates used in every training and test segment. It computes MAE (mean absolute error) and RMSE (root mean squared error) for both baselines per fold and across all predictions.

Run the test suite and syntax check:

    python3 -m unittest discover -s tests -v
    python3 -m py_compile backtest.py tests/test_backtest.py

## Parameters

- train: number of past observations used by each model; at least 2.
- test: number of future observations per fold; at least 1.
- gap: number of observations intentionally excluded between training and testing; may be zero.
- step: how many observations to move the rolling window after a fold.
- season: repeating cycle length; at least 1 and no greater than train.

All dates must be valid ISO calendar dates and strictly increasing. Demand is finite and nonnegative. Missing calendar days are permitted, but seasonal positions follow observation order rather than weekday names.

## Methodology

Each fold uses rows indexed [start, start + train) for training and [start + train + gap, start + train + gap + test) for testing. The seasonal baseline advances its cycle by gap positions before issuing the first forecast. This prevents accidental phase shifts when an embargo window separates training and evaluation.

Absolute and squared errors are pooled across all forecasted rows to compute aggregate MAE and RMSE. If folds overlap, the report counts each evaluation occurrence separately, which is appropriate for a fold-weighted evaluation but not a unique-calendar-day metric.

## Files

- backtest.py: CSV validation, fold splitting, baseline models, metrics, CLI and JSON export.
- tests/test_backtest.py: regression and command-line tests.
- examples/daily_demand.csv: fictional daily demand with a repeating weekly pattern.

## Limitations and extensions

These are interpretable baselines, not fitted machine-learning models or a guarantee of future accuracy. In real forecasting work, account for holidays, promotions, missing dates, irregular sampling, structural breaks and model selection. Keep any final holdout period separate from iterative model tuning.
