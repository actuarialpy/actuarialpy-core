"""Large-loss and pooling primitives (claimant/claim grain).

Experience rating pools (caps) large losses so a single catastrophic claim does
not distort a group's experience. These helpers identify large losses, split
losses into a pooled (retained) portion and an excess portion at a pooling
point, and emit the excess-over-threshold data that feeds tail and aggregate
modeling.

Terminology is line-agnostic: a "loss" is any claim amount; the "pooling point"
is the cap / retention. The **excess-over-threshold** output is the documented
hand-off to the modeling satellites (a GPD tail fit in ``extremeloss``, a
severity or aggregate model in ``lossmodels``, an aggregate simulation in
``risksim``) -- this module is the deterministic front end only.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from actuarialpy.columns import as_list, validate_columns
from actuarialpy.metrics import safe_divide


def flag_large_losses(
    df: pd.DataFrame,
    loss_col: str,
    threshold: float,
    *,
    out_col: str = "is_large",
    copy: bool = True,
) -> pd.DataFrame:
    """Add a boolean column flagging losses at or above ``threshold``."""
    validate_columns(df, [loss_col])
    result = df.copy() if copy else df
    result[out_col] = result[loss_col] >= threshold
    return result


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
    experience; summing ``excess_col`` gives the pooled excess.
    """
    validate_columns(df, [loss_col])
    result = df.copy() if copy else df
    result[pooled_col] = result[loss_col].clip(upper=pooling_point)
    result[excess_col] = (result[loss_col] - pooling_point).clip(lower=0)
    return result


def large_loss_summary(
    df: pd.DataFrame,
    loss_col: str,
    threshold: float,
    *,
    entity_col: str | None = None,
) -> pd.DataFrame:
    """Summarize losses at or above ``threshold``.

    Returns a one-row frame: count of large losses, their total and mean, the
    share of total losses they represent, and (if ``entity_col`` given) the
    number of distinct entities with a large loss.
    """
    validate_columns(df, [loss_col] + ([entity_col] if entity_col else []))
    grand_total = df[loss_col].sum()
    large = df[df[loss_col] >= threshold]
    large_total = large[loss_col].sum()
    row = {
        "threshold": threshold,
        "large_count": int(len(large)),
        "large_total": large_total,
        "large_mean": large[loss_col].mean() if len(large) else 0.0,
        "share_of_total": float(safe_divide(large_total, grand_total)),
    }
    if entity_col:
        row["large_entities"] = int(large[entity_col].nunique())
    return pd.DataFrame([row])


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
    out_cols = keep + [loss_col]
    result = above[out_cols].copy()
    result[excess_col] = above[loss_col] - threshold
    return result.reset_index(drop=True)
