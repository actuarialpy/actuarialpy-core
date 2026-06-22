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
