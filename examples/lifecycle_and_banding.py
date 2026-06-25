"""Lifecycle and banding: experience by membership status and by group size.

Derive a first-year / active / termed status from effective and termination
dates as of a valuation date, then compare experience across those statuses;
and bucket groups into subscriber-count bands and summarize experience by band.

    pip install actuarialpy
    python lifecycle_and_banding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import actuarialpy as ap  # noqa: E402
from _sample_data import sample_member_months  # noqa: E402

EXPENSE = ["total_claims", "pharmacy_rebates", "non_ffs_expenses"]
REVENUE = ["premium"]
EXPOSURE = ["member_months"]


def section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main() -> None:
    df = sample_member_months()

    section("1. derive_status: classify members as of 2025-12-01")
    dated = ap.derive_status(
        df,
        effective_col="effective_date",
        termination_col="termination_date",
        as_of=pd.Timestamp("2025-12-01"),
        first_year_months=12,
    )
    print(dated["status"].value_counts().to_string())

    section("2. experience by membership status")
    exp = ap.Experience(
        dated, expense=EXPENSE, revenue=REVENUE, exposure=EXPOSURE,
        date="incurred_date", profile="health",
    )
    print(exp.by_status("status").to_string(index=False))

    section("3. by_band: experience by group subscriber-count band")
    bands = [0, 12, 18, 1_000]
    labels = ["small (<12)", "mid (12-17)", "large (18+)"]
    print(exp.by_band("group_subscriber_count", bands=bands, labels=labels).to_string(index=False))


if __name__ == "__main__":
    main()
