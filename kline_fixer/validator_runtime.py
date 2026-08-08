from typing import cast

import pandas as pd

from kline_fixer.validator import (
    CandleSequenceValidator,
    CloseTimeValidator,
    ColumnValidator,
    DataSource,
    OhlcBoundsValidator,
    PriceOutlierValidator,
    PriceValueValidator,
    TimestampValidator,
    ValidationReport,
    Validator,
)

DEFAULT_VALUE_COLUMNS = ("open", "high", "low", "close")
DEFAULT_OPEN_TIME_COLUMN = "open_time"
DEFAULT_CLOSE_TIME_COLUMN = "close_time"
def validate_klines(
        source: DataSource,
        *,
        interval: str | pd.Timedelta | None = None,
        outlier_zscore: float = 10.0,
        value_columns: tuple[str, ...] = DEFAULT_VALUE_COLUMNS,
        open_time_column: str = DEFAULT_OPEN_TIME_COLUMN,
        close_time_column: str = DEFAULT_CLOSE_TIME_COLUMN,
) -> ValidationReport:
    if len(value_columns) < 4:
        raise ValueError("value_columns must start with open, high, low, and close columns")

    frame = _load(source).reset_index(drop=True)
    required_columns = (*value_columns, open_time_column, close_time_column)
    columns = ColumnValidator(required_columns).validate(frame)
    if not columns.is_valid:
        return ValidationReport(columns.issues, rows_checked=len(frame))
    if len(frame) < 2:
        raise ValueError("Dataset must contain at least 2 rows")

    open_column, high_column, low_column, close_column = value_columns[:4]
    candle_interval = _find_interval(interval, _timestamps(frame[open_time_column]).dropna())
    validators: tuple[Validator, ...] = (
        TimestampValidator(open_time_column, close_time_column),
        CandleSequenceValidator(candle_interval, open_time_column),
        CloseTimeValidator(candle_interval, open_time_column, close_time_column),
        PriceValueValidator(value_columns),
        OhlcBoundsValidator(open_column, high_column, low_column, close_column),
        PriceOutlierValidator(outlier_zscore, value_columns),
    )
    issues = tuple(issue for validator in validators for issue in validator.validate(frame).issues)
    return ValidationReport(issues, candle_interval, len(frame))

def _load(source: DataSource) -> pd.DataFrame:
    return source.copy(deep=False) if isinstance(source, pd.DataFrame) else pd.read_csv(source)

def _timestamps(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() >= values.notna().sum() * 0.9:
        unit = "ms" if numeric.dropna().abs().median() > 10 ** 11 else "s"
        result = pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    else:
        result = pd.to_datetime(values, utc=True, errors="coerce")
    return cast(pd.Series, result)
def _find_interval(value: str | pd.Timedelta | None, opens: pd.Series) -> pd.Timedelta:
    if value is not None:
        result = pd.Timedelta(value)
        if not isinstance(result, pd.Timedelta) or result <= pd.Timedelta(0):
            raise ValueError("interval must be positive")
        return result

    differences = opens.sort_values().diff().dropna()
    differences = differences[differences > pd.Timedelta(0)]
    if differences.empty:
        raise ValueError("interval cannot be inferred from open times")
    return cast(pd.Timedelta, pd.Timedelta(differences.mode().iloc[0]))


def _prices(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    return frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
