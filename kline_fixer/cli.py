"""Command-line interface for kline validation."""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from .validator_runtime import (
    DEFAULT_CLOSE_TIME_COLUMN,
    DEFAULT_OPEN_TIME_COLUMN,
    DEFAULT_VALUE_COLUMNS,
    validate_klines,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find errors and anomalies in OHLC kline CSV data.")
    parser.add_argument("csv", help="CSV file to validate")
    parser.add_argument("--interval", help="Expected interval, e.g. 15min (inferred by default)")
    parser.add_argument("--outlier-zscore", type=float, default=10.0)
    parser.add_argument(
        "--value-columns", nargs="+", default=DEFAULT_VALUE_COLUMNS, metavar="COLUMN",
        help="Numeric columns; first four represent open, high, low, close (extras may include volume)",
    )
    parser.add_argument("--open-time-column", default=DEFAULT_OPEN_TIME_COLUMN)
    parser.add_argument("--close-time-column", default=DEFAULT_CLOSE_TIME_COLUMN)
    parser.add_argument("--output", help="Optional path for a findings CSV")
    args = parser.parse_args(argv)
    report = validate_klines(
        args.csv,
        interval=args.interval,
        outlier_zscore=args.outlier_zscore,
        value_columns=tuple(args.value_columns),
        open_time_column=args.open_time_column,
        close_time_column=args.close_time_column,
    )
    findings = report.to_frame()
    if args.output:
        findings.to_csv(args.output, index=False)
    if findings.empty:
        print(f"OK: checked {report.rows_checked} rows; interval={report.interval}")
        return 0
    print(findings.to_string(index=False))
    print(f"\nFound {len(report.issues)} issue(s) in {report.rows_checked} rows.")
    return 1
