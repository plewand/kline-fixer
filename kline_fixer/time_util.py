from typing import cast

import pandas as pd


def _timestamps(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() >= values.notna().sum() * 0.9:
        unit = "ms" if numeric.dropna().abs().median() > 10 ** 11 else "s"
        result = pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    else:
        result = pd.to_datetime(values, utc=True, errors="coerce")
    return cast(pd.Series, result)
