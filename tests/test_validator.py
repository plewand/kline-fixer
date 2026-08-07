from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
import pytest

from kline_fixer import validate_klines


@pytest.fixture
def valid_klines() -> pd.DataFrame:
    opens = pd.date_range("2025-01-01", periods=5, freq="15min", tz="UTC")
    open_ms = opens.astype("int64") // 1_000_000
    return pd.DataFrame(
        {"open_time": open_ms, "close_time": open_ms + 899_999, "open": [100.0, 101.0, 102.0, 103.0, 104.0],
         "high": [102.0, 103.0, 104.0, 105.0, 106.0], "low": [99.0, 100.0, 101.0, 102.0, 103.0],
         "close": [101.0, 102.0, 103.0, 104.0, 105.0]})


def codes(frame: pd.DataFrame, **kwargs: object) -> set[str]:
    return {issue.code for issue in validate_klines(frame, interval="15min", **kwargs).issues}


def test_valid_frame_has_no_findings(valid_klines: pd.DataFrame) -> None:
    report = validate_klines(valid_klines)
    assert report.is_valid
    assert report.interval == pd.Timedelta(minutes=15)
    assert report.rows_checked == 5


def test_missing_candle_is_found(valid_klines: pd.DataFrame) -> None:
    report = validate_klines(valid_klines.drop(index=2).reset_index(drop=True), interval="15min")
    issue = next(issue for issue in report.issues if issue.code == "missing_candles")
    assert (issue.row, issue.value) == (2, 1)


def test_timestamp_problems_are_found(valid_klines: pd.DataFrame) -> None:
    damaged = valid_klines.copy()
    damaged.loc[1, "close_time"] += 1
    damaged.loc[3, "open_time"] = damaged.loc[2, "open_time"]
    assert {"invalid_close_time", "duplicate_timestamp", "unordered_timestamp"} <= codes(damaged)


@pytest.mark.parametrize(("column", "value", "expected"),
                         [("open", 0.0, "non_positive_value"), ("close", np.inf, "non_finite_value"),
                          ("high", 50.0, "invalid_high"), ("low", 200.0, "invalid_low")])
def test_bad_prices_are_found(valid_klines: pd.DataFrame, column: str, value: float, expected: str) -> None:
    damaged = valid_klines.copy()
    damaged.loc[2, column] = value
    assert expected in codes(damaged)


def test_large_price_jump_is_found(valid_klines: pd.DataFrame) -> None:
    damaged = pd.concat([valid_klines] * 3, ignore_index=True)
    start = valid_klines.loc[0, "open_time"]
    damaged["open_time"] = start + damaged.index * 900_000
    damaged["close_time"] = damaged["open_time"] + 899_999
    damaged.loc[8, ["open", "high", "low", "close"]] = [1000, 1001, 999, 1000]
    report = validate_klines(damaged, interval="15min", outlier_zscore=6.0)
    outlier_columns = {issue.column for issue in report.issues if issue.code == "price_outlier"}
    assert outlier_columns == {"open", "high", "low", "close"}


def test_missing_columns_are_reported() -> None:
    report = validate_klines(pd.DataFrame({"open_time": []}))
    assert not report.is_valid
    assert {issue.column for issue in report.issues} == {"close_time", "open", "high", "low", "close"}


def test_custom_column_names_and_extra_value_column(valid_klines: pd.DataFrame) -> None:
    renamed = valid_klines.rename(columns={
        "open_time": "started_at",
        "close_time": "ended_at",
        "open": "opening",
        "high": "maximum",
        "low": "minimum",
        "close": "closing",
    })
    renamed["volume"] = [10.0, 11.0, 12.0, 13.0, 14.0]

    report = validate_klines(
        renamed,
        value_columns=("opening", "maximum", "minimum", "closing", "volume"),
        open_time_column="started_at",
        close_time_column="ended_at",
    )

    assert report.is_valid


def test_cli_accepts_custom_columns(valid_klines: pd.DataFrame, tmp_path: Path) -> None:
    from kline_fixer.cli import main

    renamed = valid_klines.rename(columns={
        "open_time": "started_at", "close_time": "ended_at",
        "open": "opening", "high": "maximum", "low": "minimum", "close": "closing",
    })
    renamed["volume"] = [10.0, 11.0, 12.0, 13.0, 14.0]
    csv = tmp_path / "custom.csv"
    renamed.to_csv(csv, index=False)

    result = main([
        str(csv), "--value-columns", "opening", "maximum", "minimum", "closing", "volume",
        "--open-time-column", "started_at", "--close-time-column", "ended_at",
    ])

    assert result == 0
