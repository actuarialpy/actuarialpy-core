"""Large-loss pooling and the excess-over-threshold modeling hand-off.

Experience rating pools (caps) large losses so a single catastrophic claim does
not distort a group's experience. These helpers are the deterministic transform
that capping requires: ``pool_losses`` splits each loss into a pooled (retained)
portion and an excess portion at a pooling point, and ``excess_over_threshold``
emits the per-claim excess sample that feeds tail and aggregate modeling.

Terminology is line-agnostic: a "loss" is any claim amount; the "pooling point"
is the cap / retention. The ``excess_over_threshold`` output is the documented
hand-off to the modeling satellites (a GPD tail fit in ``extremeloss``, a
severity or aggregate model in ``lossmodels``, an aggregate simulation in
``risksim``). For descriptive large-claim flagging and concentration, see
``actuarialpy.claimants``.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from actuarialpy.columns import as_list, validate_columns


def pool_losses(
    df: pd.DataFrame,
    loss_col: str,
    pooling_point: float,
    *,
    pooled_col: str = "pooled_loss",
    excess_col: str = "excess_loss",
    copy: bool = True,
) -> pd.DataFrame:
    """Split each loss into a pooled (capped) portion and an excess portion.

    ``pooled = min(loss, pooling_point)`` is the retained amount used in the
    group's experience; ``excess = max(loss - pooling_point, 0)`` is the portion
    pooled across the block. Summing ``pooled_col`` by group gives capped
    experience; summing ``excess_col`` gives the pooled excess. The input is
    typically one row per claimant (e.g. the output of ``summarize_claimants``).
    """
    validate_columns(df, [loss_col])
    result = df.copy() if copy else df
    result[pooled_col] = result[loss_col].clip(upper=pooling_point)
    result[excess_col] = (result[loss_col] - pooling_point).clip(lower=0)
    return result


def excess_over_threshold(
    df: pd.DataFrame,
    loss_col: str,
    threshold: float,
    *,
    keep_cols: str | Iterable[str] | None = None,
    excess_col: str = "excess",
) -> pd.DataFrame:
    """Return losses strictly above ``threshold`` with their excess amount.

    ``excess = loss - threshold`` for rows where ``loss > threshold``. This is
    the excess-over-threshold sample used to fit a tail (e.g. a generalized
    Pareto distribution in ``extremeloss``) or a severity distribution in
    ``lossmodels``; the threshold is the EVT exceedance threshold / pooling
    point. ``keep_cols`` carries identifier or covariate columns through.
    """
    keep = as_list(keep_cols)
    validate_columns(df, [loss_col] + keep)
    above = df[df[loss_col] > threshold].copy()
    result = above[keep + [loss_col]].copy()
    result[excess_col] = above[loss_col] - threshold
    return result.reset_index(drop=True)


def _retention_moments(outcomes):
    """Sort the outcome sample and precompute prefix sums for fast capped moments."""
    x = np.sort(np.asarray(outcomes, dtype=float))
    if x.size == 0:
        raise ValueError("outcomes is empty")
    csum = np.concatenate(([0.0], np.cumsum(x)))
    csum2 = np.concatenate(([0.0], np.cumsum(x * x)))
    return x, csum, csum2


def _retained_cv_at(sorted_x, csum, csum2, retention, n_units):
    """CV of the retained aggregate at one or more retention levels (vectorized)."""
    n = sorted_x.size
    u = np.asarray(retention, dtype=float)
    k = np.searchsorted(sorted_x, u, side="right")            # count of outcomes <= u
    rem = n - k
    mean = (csum[k] + rem * u) / n                             # E[min(X, u)]
    e2 = (csum2[k] + rem * u * u) / n                          # E[min(X, u)^2]
    var = np.maximum(e2 - mean * mean, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = np.where(mean > 0, np.sqrt(var) / mean, np.nan)
    return cv / np.sqrt(n_units)


def retained_cv(outcomes, retention, *, n_units=1):
    """Coefficient of variation of the retained aggregate of ``n_units`` iid units.

    Each unit's outcome is retained (capped) at ``retention`` -- ``min(outcome,
    retention)`` -- and ``n_units`` such units are summed. For independent units
    this CV is ``cv(min(X, retention)) / sqrt(n_units)``, where ``X`` is drawn from
    the per-unit outcome sample ``outcomes`` (array-like). Capping discards
    everything above ``retention``, so only the body of ``outcomes`` matters.

    Parameters
    ----------
    outcomes : array-like
        Per-unit outcome sample (e.g. one value per member-year, claim, or risk).
    retention : float or array-like
        Cap applied to each unit. Scalar returns a float; an array returns the CV
        at each retention.
    n_units : int, default 1
        Number of independent units in the aggregate.

    Returns
    -------
    float or numpy.ndarray
        Coefficient of variation of the retained aggregate.
    """
    x, csum, csum2 = _retention_moments(outcomes)
    cv = _retained_cv_at(x, csum, csum2, retention, n_units)
    return float(cv) if np.ndim(retention) == 0 else cv


def retention_for_target_cv(outcomes, n_units, target_cv, *, bounds=None, n_grid=256):
    """Retention at which the retained aggregate of ``n_units`` units hits a target CV.

    Inverts :func:`retained_cv`. The single-unit retained CV increases with the
    retention, so this solves ``retained_cv(outcomes, u, n_units=n_units) ==
    target_cv`` for the retention ``u`` by interpolation over a grid spanning
    ``bounds`` (default ``min..max`` of ``outcomes``). Targets below or above the
    achievable range clamp to the lower or upper bound. Holding ``target_cv`` fixed,
    a larger ``n_units`` yields a higher retention (more independent units stabilize
    the aggregate, so less needs to be capped) -- i.e. the basis for a size-graded
    retention rule.

    Parameters
    ----------
    outcomes : array-like
        Per-unit outcome sample.
    n_units : int
        Number of independent units in the aggregate.
    target_cv : float
        Desired coefficient of variation of the retained aggregate.
    bounds : tuple(float, float), optional
        ``(lo, hi)`` retention search bounds. Defaults to the min and max of
        ``outcomes``.
    n_grid : int, default 256
        Number of grid points spanning ``bounds``.

    Returns
    -------
    float
        The retention level, clamped to ``bounds``.
    """
    x, csum, csum2 = _retention_moments(outcomes)
    lo = float(bounds[0]) if bounds is not None else float(x[0])
    hi = float(bounds[1]) if bounds is not None else float(x[-1])
    grid = np.linspace(lo, hi, int(n_grid))
    cvx = np.maximum.accumulate(_retained_cv_at(x, csum, csum2, grid, n_units=1))
    target_cvx = float(target_cv) * np.sqrt(n_units)
    u = float(np.interp(target_cvx, cvx, grid))
    return float(np.clip(u, lo, hi))
