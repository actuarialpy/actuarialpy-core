"""Small DataFrame validation helpers.

ActuarialPy intentionally avoids wrapping ordinary pandas operations unless the
helper adds validation or actuarial-specific safeguards.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


def as_list(value: Any) -> list[Any]:
    """Return value as a list. Strings are treated as single values."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
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


def grouped_factor_lookup(
    df: pd.DataFrame,
    factors: pd.DataFrame,
    by: str | Iterable[str],
    key_values: Any,
    *,
    key_col: str,
    factor_col: str,
) -> np.ndarray:
    """Look up a per-segment factor by ``(group..., key)``, joining by value.

    ``factors`` is a tidy table with grouping column(s) ``by``, a key column
    (``key_col``) and a factor column (``factor_col``). Each row of ``df`` is matched on
    its group-column values plus ``key_values`` (positional, in row order). The factor
    table must be unique on ``by + [key_col]`` -- a duplicate would fan rows out on the
    join -- so this raises otherwise. Returns a float array with ``NaN`` where the
    ``(group, key)`` pair is absent; the frame's own index never participates, so order
    is preserved regardless of index.
    """
    by_cols = as_list(by)
    if not by_cols:
        raise ValueError("Pass by=... naming the grouping column(s) for a per-segment factor table.")
    validate_columns(factors, by_cols + [key_col, factor_col])
    ensure_unique_keys(factors, by_cols + [key_col], name="factor table")
    lookup = factors.set_index(by_cols + [key_col])[factor_col]
    key_frame = df[by_cols].reset_index(drop=True).copy()
    key_frame[key_col] = key_values
    row_keys = pd.MultiIndex.from_frame(key_frame[by_cols + [key_col]])
    return np.array(lookup.reindex(row_keys), dtype="float64")


def sum_columns(df: pd.DataFrame, cols: str | Iterable[str], *, min_count: int = 1) -> pd.Series:
    """Validate and sum one or more DataFrame columns row-wise.

    This is kept as a small internal-friendly utility because many actuarial
    functions accept several expense or revenue columns. For simple user code,
    pandas syntax such as ``df[cols].sum(axis=1)`` is usually sufficient.
    """
    cols_list = as_list(cols)
    if not cols_list:
        raise ValueError("cols must contain at least one column")
    validate_columns(df, cols_list)
    return df[cols_list].sum(axis=1, min_count=min_count)


_DATE_NAME_TOKENS = {"date", "month", "period", "year", "quarter", "week", "yearmonth", "yyyymm"}
_DATE_AFFIX_TOKENS = ("date", "month", "period", "quarter", "week", "year")


def is_date_like(series: pd.Series, name: str) -> bool:
    """Heuristic test for a date/time column.

    Returns True if the column has a datetime or period dtype, or its name matches a
    common date token (e.g. ``month``, ``paid_month``, ``effective_date``). Used to
    place date columns first in summary output.
    """
    if pd.api.types.is_datetime64_any_dtype(series) or isinstance(series.dtype, pd.PeriodDtype):
        return True
    lowered = name.lower()
    if lowered in _DATE_NAME_TOKENS:
        return True
    return any(lowered.startswith(tok + "_") or lowered.endswith("_" + tok) for tok in _DATE_AFFIX_TOKENS)
