"""Rolling-period actuarial summaries."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from actuarialpy.columns import EXPOSURE_SUFFIX, as_list, validate_columns
from actuarialpy.experience import summarize_experience
from actuarialpy.metrics import loss_ratio, per_exposure


def _per_exposure_column_names(exposure: str) -> tuple[str, str]:
    suffix = EXPOSURE_SUFFIX.get(exposure)
    if suffix:
        return f"expense_{suffix}", f"revenue_{suffix}"
    return f"total_expense_per_{exposure}", f"total_revenue_per_{exposure}"


def rolling_summary(
    df: pd.DataFrame,
    *,
    date_col: str,
    window: int = 12,
    groupby: str | Iterable[str] | None = None,
    expense_cols: str | Iterable[str],
    revenue_cols: str | Iterable[str],
    exposure_cols: str | Iterable[str] | None = None,
    freq: str | None = None,
    min_periods: int | None = None,
    drop_incomplete: bool = True,
    ratio_col: str = "loss_ratio",
) -> pd.DataFrame:
    """Calculate calendar-aware rolling sums and ratios by period and grouping.

    The window is measured in *calendar periods*, not in rows. Each group is
    reindexed onto a dense, gap-free period grid (running from that group's
    first to last observed period at frequency ``freq``) before the rolling
    window is applied, so a missing month no longer causes the window to
    silently span extra calendar time. Filled periods carry zero amounts and
    zero exposure and therefore contribute nothing to the rolling sums.

    ``freq`` is a pandas offset alias such as ``"MS"`` (month start), ``"QS"``,
    or ``"YS"``. If omitted it is inferred from the data; inference needs at
    least three distinct, regularly spaced periods. Gapped data is by
    definition not regularly spaced, so pass ``freq`` explicitly in that case.

    The output includes ``period_start`` and ``period_end``. By default only
    complete windows are returned; for a 12-period window, the first output row
    appears once 12 periods are available.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    groups = as_list(groupby)
    expenses = as_list(expense_cols)
    revenues = as_list(revenue_cols)
    exposures = as_list(exposure_cols)
    validate_columns(df, groups + [date_col] + expenses + revenues + exposures)
    min_periods = window if min_periods is None else min_periods

    base = summarize_experience(
        df,
        groupby=groups + [date_col],
        expense_cols=expenses,
        revenue_cols=revenues,
        exposure_cols=exposures,
        ratio_col="period_ratio",
    )
    base[date_col] = pd.to_datetime(base[date_col])

    if freq is None:
        unique_dates = base[date_col].drop_duplicates().sort_values()
        freq = pd.infer_freq(unique_dates) if len(unique_dates) >= 3 else None
        if freq is None:
            raise ValueError(
                "Could not infer the period frequency for rolling reindexing. "
                "Pass freq explicitly, e.g. freq='MS' for monthly data. Note "
                "that data with calendar gaps is not regularly spaced and "
                "always requires an explicit freq."
            )

    amount_cols = ["total_expense", "total_revenue"] + exposures
    pieces = []
    iterator = base.groupby(groups, dropna=False, sort=False) if groups else [((), base)]

    for key, part in iterator:
        key_tuple = key if isinstance(key, tuple) else (key,)
        part = part.sort_values(date_col).set_index(date_col)
        full_idx = pd.date_range(part.index.min(), part.index.max(), freq=freq)
        part = part.reindex(full_idx)
        part[amount_cols] = part[amount_cols].fillna(0.0)

        n = len(full_idx)
        rolled = part[amount_cols].rolling(window=window, min_periods=min_periods).sum()

        out = pd.DataFrame(index=range(n))
        for col, value in zip(groups, key_tuple):
            # value is a groupby key (Hashable); pandas-stubs does not match the
            # scalar-broadcast __setitem__ overload for it. Valid at runtime.
            out[col] = value  # type: ignore[call-overload]
        out["period_start"] = [full_idx[max(0, i - window + 1)] for i in range(n)]
        out["period_end"] = list(full_idx)
        out["months_available"] = [min(i + 1, window) for i in range(n)]
        for col in amount_cols:
            out[col] = rolled[col].values
        out[ratio_col] = loss_ratio(out["total_expense"], out["total_revenue"])
        for exposure in exposures:
            expense_per, revenue_per = _per_exposure_column_names(exposure)
            out[expense_per] = per_exposure(out["total_expense"], out[exposure])
            out[revenue_per] = per_exposure(out["total_revenue"], out[exposure])

        if drop_incomplete:
            out = out[out["months_available"] >= window].copy()
        pieces.append(out)

    if not pieces:
        return pd.DataFrame()
    result = pd.concat(pieces, ignore_index=True)
    if drop_incomplete:
        result = result.drop(columns=["months_available"])
    return result
