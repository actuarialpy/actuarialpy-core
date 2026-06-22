"""Small DataFrame validation helpers.

ActuarialPy intentionally avoids wrapping ordinary pandas operations unless the
helper adds validation or actuarial-specific safeguards.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd


def as_list(value: Any) -> list[Any]:
    """Return value as a list. Strings are treated as single values.

    Sets are returned in a deterministic (string-sorted) order, since set
    iteration order is otherwise arbitrary and these lists frequently become
    group-by keys or output column orders.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def validate_columns(df: pd.DataFrame, cols: str | Iterable[str]) -> None:
    """Raise ValueError if any required columns are missing."""
    required = as_list(cols)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def ensure_unique_keys(df: pd.DataFrame, keys: str | Iterable[str], *, name: str = "data") -> None:
    """Raise ValueError if key columns are not unique."""
    key_list = as_list(keys)
    validate_columns(df, key_list)
    duplicates = df[df.duplicated(key_list, keep=False)]
    if not duplicates.empty:
        examples = duplicates[key_list].drop_duplicates().head(10).to_dict("records")
        raise ValueError(f"{name} has duplicate keys for {key_list}. Examples: {examples}")


def sum_columns(df: pd.DataFrame, cols: str | Iterable[str], *, min_count: int = 1) -> pd.Series:
    """Validate and sum one or more DataFrame columns row-wise.

    This is kept as a small internal-friendly utility because many actuarial
    functions accept several expense or revenue columns. For simple user code,
    pandas syntax such as ``df[cols].sum(axis=1)`` is usually sufficient.

    With ``min_count=1`` (the default), a row consisting entirely of NaN sums to
    NaN, while a row with at least one real value treats the remaining NaNs as 0.
    """
    cols_list = as_list(cols)
    if not cols_list:
        raise ValueError("cols must contain at least one column")
    validate_columns(df, cols_list)
    return df[cols_list].sum(axis=1, min_count=min_count)


# Canonical mapping from exposure column -> per-exposure metric suffix. Shared by
# experience, rolling, and components so the convention lives in exactly one place.
EXPOSURE_SUFFIX = {
    "member_months": "pmpm",
    "subscriber_months": "pspm",
    "employee_months": "pepm",
}


def per_exposure_name(base: str, exposure: str) -> str:
    """Build a per-exposure column name from a base label and an exposure column.

    ``per_exposure_name("inpatient", "member_months")`` -> ``"inpatient_pmpm"``.
    Unrecognized exposures fall back to ``f"{base}_per_{exposure}"``.
    """
    suffix = EXPOSURE_SUFFIX.get(exposure)
    return f"{base}_{suffix}" if suffix else f"{base}_per_{exposure}"
