"""Reserving: completion triangle -> completion factors -> ultimate / IBNR.

Build a cumulative paid-loss triangle from a long (origin, valuation, paid)
frame, derive completion (development) factors, develop each origin period to
ultimate with ``apply_completion``, and read off the IBNR reserve -- first
pooled, then per line of business with each line developed by its own pattern.

    pip install actuarialpy
    python reserving_ibnr.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actuarialpy as ap  # noqa: E402
from _sample_data import sample_claim_payments  # noqa: E402


def section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main() -> None:
    payments = sample_claim_payments()
    valuation = payments["valuation_month"].max()

    section("1. make_completion_triangle: cumulative paid by origin x development period")
    triangle = ap.make_completion_triangle(
        payments,
        origin_col="origin_month",
        valuation_col="valuation_month",
        amount_col="paid",
        cumulative=True,
    )
    with_commas = triangle.map(lambda v: f"{v:,.0f}" if v == v else "")  # NaN -> blank
    print(with_commas.to_string())

    section("2. completion_factors: proportion of ultimate emerged by each development period")
    cf = ap.completion_factors(triangle)
    print(cf.round(4).to_string())

    section("3. apply_completion: develop the latest diagonal to ultimate, then IBNR")
    # Latest diagonal: cumulative paid-to-date per origin (the triangle is truncated
    # at the latest valuation, so summing observed incremental paid gives paid-to-date).
    latest = (
        payments.groupby("origin_month")["paid"].sum()
        .reset_index().rename(columns={"paid": "paid_to_date"})
    )
    completed = ap.apply_completion(
        latest, cf,
        value_col="paid_to_date", date_col="origin_month", valuation_date=valuation,
    )
    completed["ibnr"] = ap.ibnr(completed["paid_to_date_completed"], completed["paid_to_date"])
    show = completed.rename(columns={"paid_to_date_completed": "ultimate"})
    show = show.assign(origin_month=show["origin_month"].dt.strftime("%Y-%m"))
    print(show.to_string(index=False, formatters={
        "paid_to_date": "{:,.0f}".format, "ultimate": "{:,.0f}".format, "ibnr": "{:,.0f}".format,
    }))
    print(f"\ntotal paid to date : ${completed['paid_to_date'].sum():,.0f}")
    print(f"total ultimate     : ${completed['paid_to_date_completed'].sum():,.0f}")
    print(f"total IBNR reserve  : ${completed['ibnr'].sum():,.0f}")
    print("(apply_completion reproduces ChainLadder.project's per-origin ultimate)")

    section("4. per line of business: completion_factors_by + grouped apply_completion(by=)")
    # Each line settles differently; estimate a pattern per line and develop each
    # line by its own factors in one call. The factor table is joined on
    # (line_of_business, development period); a duplicate key would be rejected, and a
    # row past its own line's last development period is taken as fully complete.
    cf_by_lob = ap.completion_factors_by(
        payments, groupby="line_of_business",
        origin_col="origin_month", valuation_col="valuation_month", amount_col="paid",
    )
    latest_by_lob = (
        payments.groupby(["line_of_business", "origin_month"])["paid"].sum()
        .reset_index().rename(columns={"paid": "paid_to_date"})
    )
    completed_by_lob = ap.apply_completion(
        latest_by_lob, cf_by_lob, by="line_of_business",
        value_col="paid_to_date", date_col="origin_month", valuation_date=valuation,
    )
    completed_by_lob["ibnr"] = ap.ibnr(
        completed_by_lob["paid_to_date_completed"], completed_by_lob["paid_to_date"]
    )
    by_lob = (
        completed_by_lob.groupby("line_of_business")
        .agg(paid_to_date=("paid_to_date", "sum"),
             ultimate=("paid_to_date_completed", "sum"),
             ibnr=("ibnr", "sum"))
        .reset_index()
    )
    print(by_lob.to_string(index=False, formatters={
        "paid_to_date": "{:,.0f}".format, "ultimate": "{:,.0f}".format, "ibnr": "{:,.0f}".format,
    }))
    # the per-line development periods at which each line is ~95% complete
    pct95 = (
        cf_by_lob[cf_by_lob["completion_factor"] >= 0.95]
        .groupby("line_of_business")["development_month"].min()
    )
    print("\nfirst development period >= 95% complete, by line:",
          {k: int(v) for k, v in pct95.items()})


if __name__ == "__main__":
    main()
