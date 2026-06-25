"""Claimant concentration and pooling.

How concentrated is spend among the largest members, who are the top claimants,
and how do you split each claimant into a pooled (capped) portion and an excess
portion above a pooling point? The excess-over-threshold sample produced here is
exactly what an EVT / large-claim model (e.g. ``extremeloss``) would fit.

    pip install actuarialpy
    python claimant_concentration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actuarialpy as ap  # noqa: E402
from _sample_data import sample_member_months  # noqa: E402

POOLING_POINT = 50_000.0
THRESHOLDS = (25_000.0, 50_000.0, 100_000.0)


def section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main() -> None:
    df = sample_member_months()

    exp = ap.Experience(
        df, expense="total_claims", revenue="premium", exposure="member_months"
    )

    section("1. claimant_concentration: how much spend sits with the top members")
    conc = exp.claimant_concentration(
        "member_id", amount_cols="total_claims", top_n=(5, 10, 25), thresholds=THRESHOLDS
    )
    print(conc.T.to_string())

    section("2. top_claimants: the 10 largest members by total claims")
    top = ap.top_claimants(df, claimant_col="member_id", amount_col="total_claims", n=10)
    print(top.to_string(index=False))

    # Per-member annual totals -> the per-claimant frame the next two steps need.
    member_totals = (
        df.groupby("member_id", as_index=False)["total_claims"].sum()
    )

    section("3. large_claimant_flags: counts/dollars over each threshold")
    flags = ap.large_claimant_flags(
        member_totals, amount_col="total_claims", thresholds=THRESHOLDS
    )
    print(flags.to_string(index=False))

    section(f"4. pool_losses: cap each claimant at the ${POOLING_POINT:,.0f} pooling point")
    pooled = ap.pool_losses(member_totals, "total_claims", POOLING_POINT)
    print(f"total claims        : ${pooled['total_claims'].sum():,.0f}")
    print(f"pooled (capped)     : ${pooled['pooled_loss'].sum():,.0f}")
    print(f"excess over pool    : ${pooled['excess_loss'].sum():,.0f}")

    section("5. excess_over_threshold: the exceedance sample for a tail model")
    exc = ap.excess_over_threshold(
        member_totals, "total_claims", POOLING_POINT, keep_cols="member_id"
    )
    print(f"members above ${POOLING_POINT:,.0f}: {len(exc)}")
    print(exc.sort_values("excess", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
