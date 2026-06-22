"""Concentration primitives.

Quantify how concentrated a book is in its largest entities. These are
grain-agnostic: rank by ``group_id`` to see how much of the block sits in the
largest groups, or by ``member_id`` / ``claimant_id`` for the classic
"top X% of members drive Y% of cost" view. Concentration matters because it
drives credibility and volatility.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

from actuarialpy.columns import as_list, validate_columns
from actuarialpy.metrics import safe_divide


def concentration_curve(
    df: pd.DataFrame,
    *,
    by_col: str,
    rank_col: str,
    value_cols: str | Iterable[str] | None = None,
    ns: Sequence[int] = (1, 3, 5, 10, 25),
) -> pd.DataFrame:
    """Cumulative totals and share for the ``n`` largest entities.

    Entities (rows grouped by ``by_col``) are ranked in descending order of
    ``rank_col`` (summed per entity). For each ``n`` in ``ns`` the result gives
    the cumulative total of every column in ``value_cols`` across the top ``n``
    entities, plus ``share`` = cumulative ``rank_col`` over the grand total.

    With ``value_cols=None`` only ``rank_col`` is cumulated, reproducing a
    top-N ladder (top 1, top 3, ...). ``n`` values larger than the entity count
    are clipped to the total.
    """
    values = as_list(value_cols) or [rank_col]
    needed = list(dict.fromkeys([rank_col] + values))
    validate_columns(df, [by_col] + needed)

    entity = df.groupby(by_col, dropna=False)[needed].sum(numeric_only=True)
    entity = entity.sort_values(rank_col, ascending=False)
    n_entities = len(entity)
    grand_total = entity[rank_col].sum()

    cumulative = entity.cumsum()
    rows = []
    for n in ns:
        k = min(n, n_entities)
        if k == 0:
            continue
        row = {"n": n, "entities": k}
        cum = cumulative.iloc[k - 1]
        for col in values:
            row[col] = cum[col]
        row["share"] = safe_divide(cum[rank_col], grand_total)
        rows.append(row)
    return pd.DataFrame(rows)


def top_n_share(df: pd.DataFrame, *, by_col: str, amount_col: str, n: int = 1) -> float:
    """Share of total ``amount_col`` attributable to the ``n`` largest entities."""
    validate_columns(df, [by_col, amount_col])
    entity = df.groupby(by_col, dropna=False)[amount_col].sum()
    total = entity.sum()
    top = entity.sort_values(ascending=False).head(n).sum()
    return float(safe_divide(top, total))


def concentration_summary(
    df: pd.DataFrame,
    *,
    by_col: str,
    amount_col: str,
    ns: Sequence[int] = (1, 3, 5, 10, 25),
) -> pd.DataFrame:
    """Tidy concentration table: cumulative amount and share for each ``n``.

    A thin wrapper over :func:`concentration_curve` for the common single-metric
    case, returning columns ``n``, ``entities``, ``<amount_col>`` (cumulative),
    and ``share``.
    """
    return concentration_curve(df, by_col=by_col, rank_col=amount_col, ns=ns)
