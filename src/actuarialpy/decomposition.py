"""Frequency-severity and PMPM trend decomposition.

Splits a per-member cost (PMPM / pure premium) into its utilization and unit-cost
drivers, and decomposes the change between two periods into a utilization effect and
a unit-cost effect -- the standard "how much of the trend is utilization vs unit
cost" exhibit. Decomposing requires a claim (or service) count alongside losses and
exposure.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from actuarialpy.columns import as_list, validate_columns
from actuarialpy.metrics import frequency, per_exposure, safe_divide, severity, utilization_per_1000


def frequency_severity_summary(
    df: pd.DataFrame,
    *,
    count_col: str,
    loss_col: str,
    exposure_col: str,
    groupby: str | Iterable[str] | None = None,
    annualization: float = 12,
) -> pd.DataFrame:
    """Per-group claim frequency, severity, and PMPM.

    Counts, losses, and exposure are aggregated first, then the rates are derived
    after aggregation (avoiding averaging row-level rates). The identity
    ``pmpm == frequency * severity`` holds for every row. ``frequency`` is claims per
    exposure unit (per member month for monthly data), ``severity`` is loss per claim,
    ``util_per_1000`` is annualized claims per 1,000 members, and ``pmpm`` is loss per
    exposure unit.
    """
    groups = as_list(groupby)
    validate_columns(df, groups + [count_col, loss_col, exposure_col])
    amount_cols = [count_col, loss_col, exposure_col]
    if groups:
        summary = df[groups + amount_cols].groupby(groups, dropna=False, as_index=False).sum(numeric_only=True)
    else:
        summary = pd.DataFrame({col: [df[col].sum()] for col in amount_cols})

    summary["frequency"] = frequency(summary[count_col], summary[exposure_col])
    summary["severity"] = severity(summary[loss_col], summary[count_col])
    summary["util_per_1000"] = utilization_per_1000(summary[count_col], summary[exposure_col], annualization=annualization)
    summary["pmpm"] = per_exposure(summary[loss_col], summary[exposure_col])

    ordered = groups + [exposure_col, count_col, loss_col, "frequency", "severity", "util_per_1000", "pmpm"]
    return summary[[col for col in ordered if col in summary.columns]]


def decompose_pmpm_trend(
    prior: pd.DataFrame,
    current: pd.DataFrame,
    *,
    count_col: str,
    loss_col: str,
    exposure_col: str,
    on: str | Iterable[str] | None = None,
    annualization: float = 12,
) -> pd.DataFrame:
    """Decompose the PMPM change from ``prior`` to ``current`` into utilization and cost.

    Both frames are summarized with :func:`frequency_severity_summary` (optionally by
    the ``on`` keys) and aligned. The decomposition is reported two exact ways:

    - **Multiplicative trend**: ``pmpm_trend == util_trend * cost_trend``, where
      ``util_trend`` is the frequency ratio and ``cost_trend`` the severity ratio.
      This is the "PMPM grew X%, of which U% utilization and C% unit cost" view.
    - **Additive dollars**: ``pmpm_change == util_effect + cost_effect`` via a
      symmetric (midpoint) split, so the utilization and unit-cost dollar
      contributions sum exactly to the total PMPM change.
    """
    keys = as_list(on)
    p = frequency_severity_summary(
        prior, count_col=count_col, loss_col=loss_col, exposure_col=exposure_col,
        groupby=on, annualization=annualization,
    )
    c = frequency_severity_summary(
        current, count_col=count_col, loss_col=loss_col, exposure_col=exposure_col,
        groupby=on, annualization=annualization,
    )
    keep = ["frequency", "severity", "pmpm"]
    if keys:
        merged = p[keys + keep].merge(c[keys + keep], on=keys, how="outer", suffixes=("_prior", "_current"))
    else:
        merged = pd.concat(
            [p[keep].add_suffix("_prior").reset_index(drop=True),
             c[keep].add_suffix("_current").reset_index(drop=True)],
            axis=1,
        )

    merged["util_trend"] = safe_divide(merged["frequency_current"], merged["frequency_prior"])
    merged["cost_trend"] = safe_divide(merged["severity_current"], merged["severity_prior"])
    merged["pmpm_trend"] = safe_divide(merged["pmpm_current"], merged["pmpm_prior"])

    freq_mean = (merged["frequency_prior"] + merged["frequency_current"]) / 2
    sev_mean = (merged["severity_prior"] + merged["severity_current"]) / 2
    merged["pmpm_change"] = merged["pmpm_current"] - merged["pmpm_prior"]
    merged["util_effect"] = (merged["frequency_current"] - merged["frequency_prior"]) * sev_mean
    merged["cost_effect"] = (merged["severity_current"] - merged["severity_prior"]) * freq_mean

    ordered = keys + [
        "pmpm_prior", "pmpm_current", "pmpm_trend", "util_trend", "cost_trend",
        "pmpm_change", "util_effect", "cost_effect",
        "frequency_prior", "frequency_current", "severity_prior", "severity_current",
    ]
    return merged[[col for col in ordered if col in merged.columns]]
