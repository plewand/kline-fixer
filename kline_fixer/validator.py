from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeAlias

import numpy as np
import pandas as pd

from kline_fixer.time_util import _timestamps

DataSource: TypeAlias = pd.DataFrame | str | Path


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    row: int | None
    column: str | None
    message: str
    value: object = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[Issue, ...]

    interval: pd.Timedelta | None = None
    rows_checked: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            (asdict(issue) for issue in self.issues),
            columns=np.array(["code", "row", "column", "message", "value"]),
        )

    @classmethod
    def valid(cls) -> ValidationReport:
        return ValidationReport(())


class Validator(ABC):
    @abstractmethod
    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        ...


class ColumnValidator(Validator):
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.columns = columns

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        missing = sorted({*self.columns} - set(frame.columns))
        if missing:
            return ValidationReport(tuple(
                Issue("missing_column", None, column, f"Required column {column!r} is missing") for column in missing))
        return ValidationReport.valid()


def _prices(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    return frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")


class TimestampValidator(Validator):
    def __init__(self, open_time_column: str, close_time_column: str) -> None:
        self.open_time_column = open_time_column
        self.close_time_column = close_time_column

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        issues = []
        for column in (self.open_time_column, self.close_time_column):
            parsed = _timestamps(frame[column])
            issues.extend(
                Issue("invalid_timestamp", int(row), column, "Timestamp cannot be parsed", frame.at[row, column])
                for row in frame.index[parsed.isna()]
            )
        return ValidationReport(tuple(issues))


class CandleSequenceValidator(Validator):
    def __init__(self, interval: pd.Timedelta | None, open_time_column: str) -> None:
        self.interval = interval
        self.open_time_column = open_time_column

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        opens = _timestamps(frame[self.open_time_column])
        issues = [
            Issue("duplicate_timestamp", int(row), self.open_time_column, "Duplicate candle open time",
                  frame.at[row, self.open_time_column])
            for row in frame.index[opens.duplicated(keep=False) & opens.notna()]
        ]
        for row in range(1, len(frame)):
            previous, current = opens.iloc[row - 1], opens.iloc[row]
            if pd.isna(previous) or pd.isna(current):
                continue
            if current <= previous:
                issues.append(Issue("unordered_timestamp", row, self.open_time_column,
                                    "Open times are not strictly increasing", frame.at[row, self.open_time_column]))
            if self.interval is None:
                continue
            difference = current - previous
            if difference > self.interval:
                count = int(difference / self.interval) - 1
                issues.append(Issue("missing_candles", row, self.open_time_column,
                                    f"{count} candle(s) missing before this row", count))
            elif pd.Timedelta(0) < difference < self.interval:
                issues.append(Issue("off_grid_timestamp", row, self.open_time_column,
                                    "Open time is not on the expected interval", frame.at[row, self.open_time_column]))
        return ValidationReport(tuple(issues))


class CloseTimeValidator(Validator):
    def __init__(self, interval: pd.Timedelta | None, open_time_column: str, close_time_column: str) -> None:
        self.interval = interval
        self.open_time_column = open_time_column
        self.close_time_column = close_time_column

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        if self.interval is None:
            return ValidationReport.valid()
        opens = _timestamps(frame[self.open_time_column])
        closes = _timestamps(frame[self.close_time_column])
        expected = opens + self.interval - pd.Timedelta(milliseconds=1)
        rows = frame.index[opens.notna() & closes.notna() & (closes != expected)]
        return ValidationReport(tuple(
            Issue("invalid_close_time", int(row), self.close_time_column,
                  "Close time does not match candle interval", frame.at[row, self.close_time_column])
            for row in rows
        ))


class PriceValueValidator(Validator):
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.columns = columns

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        prices = _prices(frame, self.columns)
        issues = []
        for column in self.columns:
            issues.extend(
                Issue("non_finite_value", int(row), column, "Price must be a finite number", frame.at[row, column])
                for row in frame.index[~np.isfinite(prices[column])]
            )
            issues.extend(
                Issue("non_positive_value", int(row), column, "Price must be greater than zero", frame.at[row, column])
                for row in frame.index[prices[column] <= 0]
            )
        return ValidationReport(tuple(issues))


class OhlcBoundsValidator(Validator):
    def __init__(self, open_column: str, high_column: str, low_column: str, close_column: str) -> None:
        self.open_column = open_column
        self.high_column = high_column
        self.low_column = low_column
        self.close_column = close_column

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        prices = _prices(frame, (self.open_column, self.high_column, self.low_column, self.close_column))
        finite = np.isfinite(prices).all(axis=1)
        bad_high = finite & (prices[self.high_column] < prices[[self.open_column, self.close_column, self.low_column]].max(axis=1))
        bad_low = finite & (prices[self.low_column] > prices[[self.open_column, self.close_column, self.high_column]].min(axis=1))
        issues = [
            Issue("invalid_high", int(row), self.high_column, "High is below another OHLC price",
                  frame.at[row, self.high_column])
            for row in frame.index[bad_high]
        ]
        issues.extend(
            Issue("invalid_low", int(row), self.low_column, "Low is above another OHLC price",
                  frame.at[row, self.low_column])
            for row in frame.index[bad_low]
        )
        return ValidationReport(tuple(issues))


class PriceOutlierValidator(Validator):
    def __init__(self, zscore: float, columns: tuple[str, ...]) -> None:
        self.zscore = zscore
        self.columns = columns

    def validate(self, frame: pd.DataFrame) -> ValidationReport:
        prices = _prices(frame, self.columns)
        issues: list[Issue] = []
        for column in self.columns:
            returns = prices[column].where(prices[column] > 0).map(np.log).diff()
            median = returns.median()
            mad = (returns - median).abs().median()
            if pd.isna(mad) or mad <= 0:
                continue
            robust_z = 0.6745 * (returns - median).abs() / mad
            issues.extend(
                Issue("price_outlier", int(row), column,
                      f"Unusually large {column}-to-{column} price change", frame.at[row, column])
                for row in frame.index[robust_z > self.zscore]
            )
        return ValidationReport(tuple(issues))
