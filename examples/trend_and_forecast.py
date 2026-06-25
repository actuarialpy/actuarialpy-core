"""Trend and forecast: measure prior-vs-current trend and project forward.

Compare a prior period to a current period on an exposure-adjusted basis with
``trend_summary``, then turn the observed change into an annualized trend and
project a base PMPM forward with ``project_forward``.

    pip install actuarialpy
    python trend_and_forecast.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actuarialpy as ap  # noqa: E402
from _sample_data import sample_member_months  # noqa: E402


def section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main() -> None:
    df = sample_member_months()

    section("1. trend_summary: 2024 vs 2025 claims PMPM by LOB")
    by_lob = ap.trend_summary(
        df,
        period_col="year",
        prior_period=2024,
        current_period=2025,
        amount_col="total_claims",
        exposure_col="member_months",
        groupby="line_of_business",
    )
    print(by_lob.to_string(index=False))

    section("2. trend_summary: book total (no groupby)")
    book = ap.trend_summary(
        df,
        period_col="year",
        prior_period=2024,
        current_period=2025,
        amount_col="total_claims",
        exposure_col="member_months",
    )
    print(book.to_string(index=False))

    section("3. annualize the observed change and project 12 months forward")
    prior_pmpm = float(book["prior_total_claims_per_member_months"].iloc[0])
    current_pmpm = float(book["current_total_claims_per_member_months"].iloc[0])
    annual = ap.annualized_trend(current_pmpm, prior_pmpm, months_between=12)
    projected = ap.project_forward(current_pmpm, annual, months=12)

    print(f"prior PMPM (2024)      : {prior_pmpm:,.2f}")
    print(f"current PMPM (2025)    : {current_pmpm:,.2f}")
    print(f"trend_summary 'trend'  : {float(book['trend'].iloc[0]):.3%}")
    print(f"annualized trend       : {annual:.3%}")
    print(f"12-month trend factor  : {ap.trend_factor(annual, 12):.4f}")
    print(f"projected PMPM (+12mo) : {projected:,.2f}")


if __name__ == "__main__":
    main()
