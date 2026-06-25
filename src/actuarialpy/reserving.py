"""Reserving and claims-development tools.

Claims-development primitives that sit upstream of experience analysis: development
period measurement, development (completion) triangles, the IBNR identity, and
completion-factor validation.

ActuarialPy keeps factor *estimation* and factor *application* separate. The work of
turning transactional or development data into a triangle, measuring the development
period, and the completed/paid identity lives here, alongside :func:`completion_factors`.
Applying a factor is a single multiplication, but it hinges on a join -- each row's
development period matched to the right factor -- and a factor arriving in an arbitrary
external table can be joined many ways. :func:`apply_completion` therefore commits to one
well-defined contract: factors keyed by development period, each row's development period
taken as ``development_months(incurred, valuation)`` (or an explicit ``development_col``),
joined by value so the frame's index is irrelevant and a convention mismatch surfaces as
``NaN`` rather than silent corruption. Factors from this module's own pipeline satisfy
that contract by
construction; estimate them here, then complete in your pipeline or via
``Experience.complete``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from actuarialpy.columns import as_list, grouped_factor_lookup, validate_columns


def development_months(incurred_date, valuation_date):
    """Whole months of development between incurred (origin) and valuation."""
    incurred = pd.to_datetime(incurred_date)
    valuation = pd.to_datetime(valuation_date)
    if hasattr(incurred, "dt"):
        return (valuation.dt.year - incurred.dt.year) * 12 + (valuation.dt.month - incurred.dt.month)
    return (valuation.year - incurred.year) * 12 + (valuation.month - incurred.month)


# Backwards-compatible alias: "development" is the preferred cross-domain term.
lag_months = development_months


def ibnr(completed, paid):
    """IBNR as completed minus paid (the completed/paid identity).

    Works element-wise on scalars or Series. ``completed`` and ``paid`` must be on
    the same basis; the result is the amount bridging paid-to-date to ultimate.
    """
    return completed - paid


def validate_completion_factors(
    factors: pd.DataFrame, factor_col: str = "completion_factor", *, method: str = "divide"
) -> None:
    """Validate completion-factor values for a selected convention.

    ``divide`` factors (completed = paid / factor) should satisfy
    ``0 < factor <= 1``; ``multiply`` factors (completed = paid * factor) should
    satisfy ``factor >= 1``. Useful as a sanity check on estimated factors before
    they are applied upstream.
    """
    validate_columns(factors, [factor_col])
    values = factors[factor_col]
    bad_missing = values.isna()
    if bad_missing.any():
        raise ValueError(f"{bad_missing.sum()} completion factors are missing")
    if method == "divide":
        bad = (values <= 0) | (values > 1)
        if bad.any():
            raise ValueError("divide-method completion factors should generally satisfy 0 < factor <= 1")
    elif method == "multiply":
        bad = values < 1
        if bad.any():
            raise ValueError("multiply-method completion factors should generally satisfy factor >= 1")
    else:
        raise ValueError("method must be either 'divide' or 'multiply'")


def make_completion_triangle(
    df: pd.DataFrame,
    *,
    origin_col: str,
    valuation_col: str,
    amount_col: str,
    cumulative: bool = True,
    index_name: str = "origin_period",
    development_name: str = "development_month",
) -> pd.DataFrame:
    """Build a development (completion) triangle by origin period and development period.

    Each cell aggregates ``amount_col`` for an origin month at a given valuation
    development period (whole months between origin and valuation, via :func:`development_months`).
    ``amount_col`` is treated as the *incremental* amount in each (origin, development period)
    cell; with ``cumulative=True`` -- the default, and the usual basis for
    estimating development/completion factors -- the cells are accumulated across
    development period. Set ``cumulative=False`` to return the incremental triangle, or if your
    input amounts are already cumulative-to-date snapshots.

    This consumes a compact development aggregate (one row per origin x valuation,
    i.e. months x months); it does not require transaction/line-level data.
    """
    validate_columns(df, [origin_col, valuation_col, amount_col])
    temp = df.copy()
    temp[index_name] = pd.to_datetime(temp[origin_col]).dt.to_period("M")
    temp[development_name] = development_months(temp[origin_col], temp[valuation_col])
    grouped = temp.groupby([index_name, development_name], dropna=False)[amount_col].sum().reset_index()
    triangle = grouped.pivot(index=index_name, columns=development_name, values=amount_col).sort_index(axis=1)
    if cumulative:
        triangle = triangle.cumsum(axis=1)
    return triangle


@dataclass(frozen=True)
class ChainLadder:
    """Chain-ladder development pattern fitted from a cumulative triangle.

    Fit with :meth:`fit` from a cumulative development triangle (for example the
    output of :func:`make_completion_triangle` with ``cumulative=True``):

    - ``age_to_age`` -- link (age-to-age) factors, indexed by their starting development period.
    - ``cdf`` -- cumulative development factor to ultimate by development period, including the
      tail.
    - ``completion_factors`` -- ``1 / cdf`` by development period: the proportion of ultimate
      emerged by each development period. These are divide-convention factors in ``(0, 1]``
      (``completed = paid / factor``), so they line up with
      :func:`validate_completion_factors` and downstream completion.

    Use :meth:`project` to apply the pattern to a triangle and get per-origin
    ultimate and IBNR.
    """

    age_to_age: pd.Series
    cdf: pd.Series
    completion_factors: pd.Series
    tail: float
    method: str

    @classmethod
    def fit(cls, triangle: pd.DataFrame, *, method: str = "volume", tail: float = 1.0) -> ChainLadder:
        """Estimate the development pattern from a cumulative triangle.

        ``method`` is ``"volume"`` (volume-weighted age-to-age factors, the
        default) or ``"simple"`` (straight average of individual link ratios).
        ``tail`` (>= 1) extends development beyond the latest observed development period.
        """
        if method not in ("volume", "simple"):
            raise ValueError("method must be 'volume' or 'simple'")
        if tail < 1.0:
            raise ValueError("tail must be >= 1.0")
        if not isinstance(triangle, pd.DataFrame):
            raise TypeError("triangle must be a pandas DataFrame")

        tri = triangle.sort_index(axis=1)
        cols = list(tri.columns)
        if len(cols) < 2:
            raise ValueError("triangle must have at least two development periods")
        if tri.shape[0] < 2:
            raise ValueError("triangle must have at least two origin periods")

        # age-to-age (link) factors between each pair of adjacent development periods
        ratios: dict[object, float] = {}
        for start, end in zip(cols[:-1], cols[1:]):
            pair = tri[[start, end]].dropna()
            if pair.empty:
                raise ValueError(f"no overlapping origins to estimate the {start}->{end} development factor")
            if method == "volume":
                start_sum = float(pair[start].sum())
                if start_sum == 0:
                    raise ValueError(f"zero cumulative at development period {start}; cannot estimate {start}->{end} factor")
                ratios[start] = float(pair[end].sum()) / start_sum
            else:
                ratios[start] = float((pair[end] / pair[start]).mean())
        age_to_age = pd.Series(ratios, name="age_to_age")

        # cumulative development factors to ultimate (with tail), accumulating back
        cdf_vals: dict[object, float] = {cols[-1]: float(tail)}
        running = float(tail)
        for start in reversed(cols[:-1]):
            running *= age_to_age[start]
            cdf_vals[start] = running
        cdf = pd.Series(cdf_vals, name="cdf").reindex(cols)

        completion = (1.0 / cdf).rename("completion_factor")
        return cls(
            age_to_age=age_to_age,
            cdf=cdf,
            completion_factors=completion,
            tail=float(tail),
            method=method,
        )

    def project(self, triangle: pd.DataFrame) -> pd.DataFrame:
        """Project ultimate and IBNR per origin by applying the fitted pattern.

        For each origin, takes its latest observed cumulative amount and multiplies
        by the cumulative development factor at that development period. Returns one row per origin
        with the latest development period, latest cumulative, development factor applied,
        ultimate, and IBNR (ultimate minus latest).
        """
        tri = triangle.sort_index(axis=1)
        records: list[dict[str, float]] = []
        origins: list[object] = []
        for origin, row in tri.iterrows():
            observed = row.dropna()
            if observed.empty:
                continue
            latest_development = max(observed.index)
            if latest_development not in self.cdf.index:
                raise ValueError(f"no development factor for development period {latest_development}; fit on a matching triangle")
            latest = float(observed.loc[latest_development])
            factor = float(self.cdf.loc[latest_development])
            ultimate = latest * factor
            origins.append(origin)
            records.append({
                "latest_development": latest_development,
                "latest": latest,
                "development_factor": factor,
                "ultimate": ultimate,
                "ibnr": ultimate - latest,
            })
        return pd.DataFrame.from_records(records, index=pd.Index(origins, name=tri.index.name))


def completion_factors(triangle: pd.DataFrame, *, method: str = "volume", tail: float = 1.0) -> pd.Series:
    """Completion factors by development period, via chain-ladder.

    Convenience wrapper around :class:`ChainLadder`: returns the proportion of
    ultimate emerged by each development period (``1 / cdf``) estimated from a cumulative
    triangle. Divide-convention factors in ``(0, 1]`` (``completed = paid /
    factor``). See :class:`ChainLadder` for the full pattern and per-origin
    ultimate/IBNR.
    """
    return ChainLadder.fit(triangle, method=method, tail=tail).completion_factors


def apply_completion(
    df: pd.DataFrame,
    factors: pd.Series | pd.DataFrame,
    *,
    value_col: str,
    date_col: str | None = None,
    valuation_date: Any = None,
    development_col: str | None = None,
    by: str | list[str] | None = None,
    factor_col: str = "completion_factor",
    development_name: str = "development_month",
    out_col: str | None = None,
    copy: bool = True,
) -> pd.DataFrame:
    """Develop a paid amount to estimated ultimate with completion factors.

    For each row the development period is taken from ``development_col`` if supplied,
    otherwise computed as ``development_months(df[date_col], valuation_date)`` -- the
    convention :func:`make_completion_triangle` uses, so factors from
    :func:`completion_factors` or :func:`completion_factors_by` join by construction.
    The completed amount is ``paid / factor`` (the divide convention, factors in
    ``(0, 1]``).

    ``factors`` may be either of:

    - a flat Series indexed by development period (one pattern for the whole frame), or
    - a tidy DataFrame of per-segment factors -- grouping column(s), a development-period
      column (``development_name``) and a factor column (``factor_col``), the shape
      :func:`completion_factors_by` returns -- joined on ``by`` plus development period.
      The table must be unique on ``by + [development]`` (a duplicate would fan out the
      data); this is checked.

    The join is by value, never index alignment, so the frame's own index is irrelevant.
    A row past its (group's) largest development period is taken as fully complete
    (factor ``1.0``); a development period inside the fitted range but absent stays
    ``NaN`` -- a surfaced gap; a row whose group is absent from the factor table stays
    ``NaN``; a negative development period (incurred after ``valuation_date``) raises.
    Supply either ``development_col``, or both ``date_col`` and ``valuation_date``.
    """
    if development_col is None and (date_col is None or valuation_date is None):
        raise ValueError(
            "Provide development_col, or both date_col and valuation_date, to determine each row's development period."
        )
    by_cols = as_list(by)
    needed = [value_col] + ([development_col] if development_col is not None else [date_col]) + by_cols
    validate_columns(df, needed)
    result = df.copy() if copy else df

    if development_col is not None:
        development = pd.to_numeric(result[development_col]).to_numpy()
    else:
        valuation = pd.Series(pd.to_datetime(valuation_date), index=result.index)
        development = development_months(result[date_col], valuation).to_numpy()
    if (development < 0).any():
        raise ValueError("Negative development period: some rows have an incurred date after valuation_date.")

    if isinstance(factors, pd.DataFrame):
        factor = grouped_factor_lookup(
            result, factors, by_cols, development, key_col=development_name, factor_col=factor_col
        )
        # rows past their own group's last development period are fully complete
        by_key = by_cols[0] if len(by_cols) == 1 else by_cols
        group_max = factors.groupby(by_key)[development_name].max()
        if len(by_cols) == 1:
            row_max = group_max.reindex(result[by_cols[0]].to_numpy()).to_numpy()
        else:
            row_max = group_max.reindex(pd.MultiIndex.from_frame(result[by_cols].reset_index(drop=True))).to_numpy()
        beyond = np.isnan(factor) & (development > row_max)  # absent group -> row_max NaN -> stays NaN
        factor[beyond] = 1.0
    else:
        max_development = int(pd.Index(factors.index).max())
        factor = np.array(pd.Series(development).map(factors), dtype="float64")  # NaN where absent
        factor[development > max_development] = 1.0  # beyond the fitted triangle -> complete

    result[out_col or f"{value_col}_completed"] = result[value_col].to_numpy() / factor
    return result


class InsufficientDataWarning(UserWarning):
    """Emitted when a segment has too little data to fit and is skipped or aggregated.

    Filter it with the standard :mod:`warnings` machinery, e.g.
    ``warnings.filterwarnings("ignore", category=InsufficientDataWarning)``.
    """


def chain_ladder_by(
    df: pd.DataFrame,
    *,
    groupby: str | list[str],
    origin_col: str,
    valuation_col: str,
    amount_col: str,
    cumulative: bool = True,
    method: str = "volume",
    tail: float = 1.0,
    on_insufficient: str = "raise",
    warn: bool = True,
) -> dict[Any, ChainLadder]:
    """Fit a chain-ladder development pattern per segment of ``df``.

    Groups ``df`` by ``groupby``, builds a development triangle for each segment
    (see :func:`make_completion_triangle`), and fits a :class:`ChainLadder` to
    each. Returns ``{segment_key: ChainLadder}`` -- the key is a scalar for a
    single grouping column, or a tuple for several.

    Segments too small to fit (fewer than two origins or development periods, a zero cumulative,
    and so on) are handled by ``on_insufficient``:

    - ``"raise"`` (default): raise a ``ValueError`` naming the failing segment.
    - ``"skip"``: omit those segments from the result.
    - ``"aggregate"``: use the pooled pattern fit on the whole frame for them.

    When ``on_insufficient`` is ``"skip"`` or ``"aggregate"`` and ``warn`` is true,
    an :class:`InsufficientDataWarning` naming the affected segments is emitted;
    ``warn=False`` suppresses it (the standard :mod:`warnings` filters also apply).
    To ignore thin segments entirely, use ``on_insufficient="skip", warn=False``.
    """
    if on_insufficient not in ("raise", "skip", "aggregate"):
        raise ValueError("on_insufficient must be 'raise', 'skip', or 'aggregate'")
    group_cols = as_list(groupby)
    if not group_cols:
        raise ValueError("groupby must name at least one column")
    validate_columns(df, group_cols + [origin_col, valuation_col, amount_col])

    def _fit(frame: pd.DataFrame) -> ChainLadder:
        triangle = make_completion_triangle(
            frame,
            origin_col=origin_col,
            valuation_col=valuation_col,
            amount_col=amount_col,
            cumulative=cumulative,
        )
        return ChainLadder.fit(triangle, method=method, tail=tail)

    aggregate_pattern: ChainLadder | None = None
    if on_insufficient == "aggregate":
        try:
            aggregate_pattern = _fit(df)
        except ValueError as exc:
            raise ValueError(f"cannot fit the aggregate fallback pattern: {exc}") from exc

    by_key = group_cols if len(group_cols) > 1 else group_cols[0]
    patterns: dict[Any, ChainLadder] = {}
    insufficient: list[Any] = []
    for key, part in df.groupby(by_key, sort=True):
        try:
            patterns[key] = _fit(part)
        except ValueError as exc:
            if on_insufficient == "raise":
                raise ValueError(f"segment {key!r} cannot be fit: {exc}") from exc
            insufficient.append(key)
            if on_insufficient == "aggregate" and aggregate_pattern is not None:
                patterns[key] = aggregate_pattern

    if insufficient and warn:
        action = "using the aggregate pattern for" if on_insufficient == "aggregate" else "skipping"
        warnings.warn(
            f"{action} {len(insufficient)} segment(s) with insufficient data: {insufficient}",
            InsufficientDataWarning,
            stacklevel=2,
        )
    return patterns


def completion_factors_by(
    df: pd.DataFrame,
    *,
    groupby: str | list[str],
    origin_col: str,
    valuation_col: str,
    amount_col: str,
    cumulative: bool = True,
    method: str = "volume",
    tail: float = 1.0,
    on_insufficient: str = "raise",
    warn: bool = True,
    development_name: str = "development_month",
) -> pd.DataFrame:
    """Completion factors per segment as a tidy table.

    Convenience over :func:`chain_ladder_by`: one row per (segment, development period) with the
    completion factor, ready to review, pivot, or join. Columns are the grouping
    column(s), ``development_name``, and ``completion_factor``. ``on_insufficient`` and
    ``warn`` behave as in :func:`chain_ladder_by`.
    """
    group_cols = as_list(groupby)
    patterns = chain_ladder_by(
        df,
        groupby=groupby,
        origin_col=origin_col,
        valuation_col=valuation_col,
        amount_col=amount_col,
        cumulative=cumulative,
        method=method,
        tail=tail,
        on_insufficient=on_insufficient,
        warn=warn,
    )
    records: list[dict[str, Any]] = []
    for key, fitted in patterns.items():
        key_tuple = key if isinstance(key, tuple) else (key,)
        key_map = dict(zip(group_cols, key_tuple))
        for development, factor in fitted.completion_factors.items():
            records.append({**key_map, development_name: development, "completion_factor": float(factor)})
    if not records:
        return pd.DataFrame(columns=group_cols + [development_name, "completion_factor"])
    return pd.DataFrame.from_records(records)
