"""Cohort and duration summaries."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from actuarialpy.columns import as_list, validate_columns
from actuarialpy.experience import summarize_experience
from actuarialpy.periods import add_duration_column, add_period_column


def cohort_summary(
    df: pd.DataFrame,
    *,
    entity_col: str,
    date_col: str,
    start_date_col: str,
    duration_months: int = 12,
    groupby: str | Iterable[str] | None = None,
    expense_cols: str | Iterable[str],
    revenue_cols: str | Iterable[str],
    exposure_cols: str | Iterable[str] | None = None,
    profile: str | None = None,
) -> pd.DataFrame:
    """Summarize each entity's first N months or cohort-duration window.

    Each entity is clipped to its own first ``duration_months`` months of duration
    (month 1 is the entity's start month), aligning entities by tenure rather than
    calendar time. The output also reports how much of that window is actually
    present, so partial (not-yet-mature) cohorts can be spotted and excluded:

    - ``months_observed``: count of distinct duration months present (1..N).
    - ``last_month``: latest experience month observed; with ``first_month`` this
      gives the available range.
    - ``complete``: whether the full window is present, i.e.
      ``months_observed == duration_months``.

    For example, to keep only cohorts with a full first year::

        cohorts = exp.cohort(entity_col="group", start_date_col="effective_date")
        mature = cohorts[cohorts["complete"]]
    """
    groups = as_list(groupby)
    validate_columns(df, [entity_col, date_col, start_date_col] + groups)
    temp = add_duration_column(df, start_date_col, date_col, duration_col="duration_month", one_based=True)
    temp = temp[(temp["duration_month"] >= 1) & (temp["duration_month"] <= duration_months)].copy()
    temp["first_month"] = pd.to_datetime(temp[start_date_col]).dt.to_period("M")
    temp["cohort_year"] = pd.to_datetime(temp[start_date_col]).dt.year

    group_keys = [entity_col, "first_month", "cohort_year"] + groups
    summary = summarize_experience(
        temp,
        groupby=group_keys,
        expense_cols=expense_cols,
        revenue_cols=revenue_cols,
        exposure_cols=exposure_cols,
        profile=profile,
    )

    coverage = (
        temp.groupby(group_keys, dropna=False)
        .agg(months_observed=("duration_month", "nunique"), last_month=(date_col, "max"))
        .reset_index()
    )
    coverage["last_month"] = pd.to_datetime(coverage["last_month"]).dt.to_period("M")
    coverage["complete"] = coverage["months_observed"] == duration_months
    summary = summary.merge(coverage, on=group_keys, how="left")

    coverage_cols = ["months_observed", "last_month", "complete"]
    metric_cols = [c for c in summary.columns if c not in group_keys and c not in coverage_cols]
    return summary[group_keys + coverage_cols + metric_cols]


def cohort_summary_by_period(
    cohort_df: pd.DataFrame,
    *,
    cohort_date_col: str = "first_month",
    freq: str = "Q",
    entity_col: str | None = None,
    expense_col: str = "total_expense",
    revenue_col: str = "total_revenue",
    exposure_cols: str | Iterable[str] | None = None,
) -> pd.DataFrame:
    """Roll entity-level cohort summaries into cohort month/quarter/year buckets."""
    temp = cohort_df.copy()
    if cohort_date_col not in temp.columns:
        raise ValueError(f"Missing required column: {cohort_date_col}")
    if isinstance(temp[cohort_date_col].iloc[0], pd.Period):
        temp["cohort_period"] = temp[cohort_date_col].dt.asfreq(freq)
    else:
        temp = add_period_column(temp, cohort_date_col, freq, "cohort_period", copy=False)
    exposures = as_list(exposure_cols)
    summary = summarize_experience(
        temp,
        groupby="cohort_period",
        expense_cols=expense_col,
        revenue_cols=revenue_col,
        exposure_cols=exposures,
    )
    if entity_col:
        counts = temp.groupby("cohort_period", dropna=False)[entity_col].nunique().reset_index(name="entity_count")
        summary = counts.merge(summary, on="cohort_period", how="right")
    return summary


def duration_summary(
    df: pd.DataFrame,
    *,
    entity_col: str,
    date_col: str,
    start_date_col: str,
    expense_cols: str | Iterable[str],
    revenue_cols: str | Iterable[str],
    exposure_cols: str | Iterable[str] | None = None,
    max_duration_month: int | None = None,
) -> pd.DataFrame:
    """Summarize experience by duration month since entity start."""
    temp = add_duration_column(df, start_date_col, date_col, duration_col="duration_month", one_based=True)
    temp = temp[temp["duration_month"] >= 1].copy()
    if max_duration_month is not None:
        temp = temp[temp["duration_month"] <= max_duration_month]
    return summarize_experience(
        temp,
        groupby="duration_month",
        expense_cols=expense_cols,
        revenue_cols=revenue_cols,
        exposure_cols=exposure_cols,
    )
