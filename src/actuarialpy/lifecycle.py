"""Policy/membership lifecycle primitives.

These derive *status* and *tenure* from effective and termination dates rather
than requiring a precomputed status label, and clip exposure to the window an
entity was actually in force during a period (the general "earned exposure"
idea). They are line-of-business agnostic: an entity may be a group, a policy,
a member, or a contract; dates may be policy effective/expiration or membership
enroll/disenroll.

Scope note: this module *derives the distinction and provides the levers*
(status, tenure, in-force windowing, earned exposure). It deliberately does not
encode differential treatment of cohorts (e.g. excluding first-year business
from a renewal blend, or weighting run-out). Those are pricing-methodology
choices that belong to the caller.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from actuarialpy.columns import validate_columns

STATUS_ACTIVE = "active"
STATUS_FIRST_YEAR = "first_year"
STATUS_TERMED = "termed"


def _to_dt(values) -> pd.Series:
    return pd.to_datetime(values)


def _months_between_series(start: pd.Series, end: pd.Series) -> pd.Series:
    """Whole month boundaries between two datetime Series (end - start), vectorized."""
    return (end.dt.year - start.dt.year) * 12 + (end.dt.month - start.dt.month)


def add_tenure(
    df: pd.DataFrame,
    effective_col: str,
    as_of,
    *,
    tenure_col: str = "tenure_months",
    one_based: bool = False,
    copy: bool = True,
) -> pd.DataFrame:
    """Add tenure in whole months from each entity's effective date to ``as_of``.

    ``as_of`` is a single reference date (e.g. the experience as-of date). With
    ``one_based=True`` an entity effective in the as-of month has tenure 1 rather
    than 0, matching "months of experience" conventions.
    """
    validate_columns(df, [effective_col])
    result = df.copy() if copy else df
    eff = _to_dt(result[effective_col])
    as_of_ts = pd.to_datetime(as_of)
    tenure = (as_of_ts.year - eff.dt.year) * 12 + (as_of_ts.month - eff.dt.month)
    result[tenure_col] = tenure + 1 if one_based else tenure
    return result


def derive_status(
    df: pd.DataFrame,
    *,
    effective_col: str,
    as_of,
    termination_col: str | None = None,
    first_year_months: int = 12,
    status_col: str = "status",
    labels: dict[str, str] | None = None,
    copy: bool = True,
) -> pd.DataFrame:
    """Derive an active / first-year / termed status as of a reference date.

    Classification (in precedence order):

    - **termed**: a termination date is present and on/before ``as_of``.
    - **first_year**: not termed and tenure (``as_of`` minus effective) is less
      than ``first_year_months``. The window is a parameter because "first year"
      means the first 12 months in some shops and the first policy year in
      others.
    - **active**: in force beyond the first-year window.

    ``labels`` optionally remaps the three canonical values, e.g.
    ``{"first_year": "First Year Account", "termed": "Term"}``.
    """
    cols = [effective_col] + ([termination_col] if termination_col else [])
    validate_columns(df, cols)
    result = df.copy() if copy else df

    eff = _to_dt(result[effective_col])
    as_of_ts = pd.to_datetime(as_of)
    tenure = (as_of_ts.year - eff.dt.year) * 12 + (as_of_ts.month - eff.dt.month)

    if termination_col:
        term = _to_dt(result[termination_col])
        termed = term.notna() & (term <= as_of_ts)
    else:
        termed = pd.Series(False, index=result.index)

    first_year = (~termed) & (tenure < first_year_months)

    status_values = np.where(termed, STATUS_TERMED, np.where(first_year, STATUS_FIRST_YEAR, STATUS_ACTIVE))
    status = pd.Series(status_values, index=result.index)
    if labels:
        status = status.map(lambda s: labels.get(s, s))
    result[status_col] = status
    return result


def is_in_force(
    df: pd.DataFrame,
    *,
    effective_col: str,
    period_start,
    period_end,
    termination_col: str | None = None,
) -> pd.Series:
    """Boolean Series: in force at any point during ``[period_start, period_end]``.

    In force when effective on/before ``period_end`` and the entity had not
    terminated before ``period_start`` (a missing termination date means still
    in force).
    """
    cols = [effective_col] + ([termination_col] if termination_col else [])
    validate_columns(df, cols)
    eff = _to_dt(df[effective_col])
    start = pd.to_datetime(period_start)
    end = pd.to_datetime(period_end)
    in_force = eff <= end
    if termination_col:
        term = _to_dt(df[termination_col])
        in_force = in_force & (term.isna() | (term >= start))
    return in_force


def add_months_in_force(
    df: pd.DataFrame,
    *,
    effective_col: str,
    period_start,
    period_end,
    termination_col: str | None = None,
    out_col: str = "months_in_force",
    copy: bool = True,
) -> pd.DataFrame:
    """Add whole months of overlap between each entity's in-force window and a period.

    The in-force window is ``[effective, termination]`` (a missing termination
    means the period end). The result is clipped to ``[period_start, period_end]``
    and floored at 0. Month counting is inclusive of both endpoint months, so a
    full coverage of an N-month period returns N.
    """
    cols = [effective_col] + ([termination_col] if termination_col else [])
    validate_columns(df, cols)
    result = df.copy() if copy else df

    start = pd.to_datetime(period_start)
    end = pd.to_datetime(period_end)

    eff = _to_dt(result[effective_col])
    if termination_col:
        term = _to_dt(result[termination_col]).fillna(end)
    else:
        term = pd.Series(end, index=result.index)

    eff_clipped = eff.clip(lower=start)
    term_clipped = term.clip(upper=end)
    months = _months_between_series(eff_clipped, term_clipped) + 1
    result[out_col] = months.clip(lower=0)
    return result


def earned_exposure(
    df: pd.DataFrame,
    exposure_col: str,
    *,
    effective_col: str,
    period_start,
    period_end,
    termination_col: str | None = None,
    period_months: int | None = None,
    out_col: str | None = None,
    copy: bool = True,
) -> pd.DataFrame:
    """Prorate a full-period exposure by the fraction of the period in force.

    ``earned = exposure * months_in_force / period_months``. Use this when each
    row carries a full-period exposure (e.g. annualized) that must be reduced for
    mid-period entry or termination. If your data is already monthly, filtering
    to in-force months with :func:`is_in_force` is usually simpler.
    """
    validate_columns(df, [exposure_col])
    result = add_months_in_force(
        df,
        effective_col=effective_col,
        termination_col=termination_col,
        period_start=period_start,
        period_end=period_end,
        out_col="_months_in_force_tmp",
        copy=copy,
    )
    if period_months is None:
        start = pd.to_datetime(period_start)
        end = pd.to_datetime(period_end)
        period_months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    name = out_col or f"earned_{exposure_col}"
    fraction = result["_months_in_force_tmp"] / period_months
    result[name] = result[exposure_col] * fraction
    return result.drop(columns="_months_in_force_tmp")
