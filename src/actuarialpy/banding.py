"""Size-banding primitives.

Bucket rows into size bands by any numeric column (subscriber count, member
count, exposure, premium, total insured value, ...) and summarize experience by
band. Band edges are always a parameter, since different analyses use different
cut points (e.g. one scheme with six buckets and a coarser one with four).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from actuarialpy.columns import validate_columns
from actuarialpy.experience import summarize_experience


def _default_labels(edges: Sequence[float]) -> list[str]:
    """Build readable labels from left-closed band edges.

    ``[0, 51, 76, 151, inf]`` -> ``["0-50", "51-75", "76-150", "151+"]``.
    """
    labels: list[str] = []
    for i in range(len(edges) - 1):
        lo = edges[i]
        hi = edges[i + 1]
        if np.isinf(hi):
            labels.append(f"{int(lo)}+")
        else:
            labels.append(f"{int(lo)}-{int(hi) - 1}")
    return labels


def assign_band(
    df: pd.DataFrame,
    value_col: str,
    bands: Sequence[float],
    *,
    labels: Sequence[str] | None = None,
    band_col: str = "band",
    right: bool = False,
    copy: bool = True,
) -> pd.DataFrame:
    """Assign each row to an ordered size band based on ``value_col``.

    ``bands`` are bin edges. For integer counts the natural form is left-closed
    (``right=False``), so ``bands=[0, 51, 76, 151, 251, 501, inf]`` yields
    ``[0, 51)``, ``[51, 76)``, .... A trailing ``float("inf")`` captures the open
    top band. The resulting column is an ordered categorical so downstream
    group-bys keep band order.
    """
    validate_columns(df, [value_col])
    edges = list(bands)
    if len(edges) < 2:
        raise ValueError("bands must contain at least two edges (one band).")
    if labels is None:
        labels = _default_labels(edges)
    if len(labels) != len(edges) - 1:
        raise ValueError(f"Expected {len(edges) - 1} labels for {len(edges)} edges, got {len(labels)}.")
    result = df.copy() if copy else df
    result[band_col] = pd.cut(
        result[value_col],
        bins=edges,
        labels=list(labels),
        right=right,
        include_lowest=True,
        ordered=True,
    )
    return result


def summarize_by_band(
    df: pd.DataFrame,
    value_col: str,
    bands: Sequence[float],
    *,
    labels: Sequence[str] | None = None,
    expense_cols: str | Iterable[str],
    revenue_cols: str | Iterable[str],
    exposure_cols: str | Iterable[str] | None = None,
    band_col: str = "band",
    ratio_col: str | None = None,
    right: bool = False,
    profile: str | None = None,
) -> pd.DataFrame:
    """Assign size bands then summarize experience grouped by band.

    Returns one row per band in band order (empty bands included), with the same
    aggregates, loss ratio, and per-exposure metrics as
    :func:`~actuarialpy.experience.summarize_experience`.
    """
    banded = assign_band(
        df,
        value_col,
        bands,
        labels=labels,
        band_col=band_col,
        right=right,
        copy=True,
    )
    summary = summarize_experience(
        banded,
        groupby=band_col,
        expense_cols=expense_cols,
        revenue_cols=revenue_cols,
        exposure_cols=exposure_cols,
        ratio_col=ratio_col,
        profile=profile,
    )
    # Preserve band order and surface empty bands explicitly.
    order = list(banded[band_col].cat.categories)
    summary[band_col] = pd.Categorical(summary[band_col], categories=order, ordered=True)
    return summary.sort_values(band_col).reset_index(drop=True)
