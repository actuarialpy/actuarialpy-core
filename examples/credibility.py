"""Credibility: blend a group's own experience with the book.

Partial credibility via a square-root rule, applied two ways: the
``credibility_weighted_estimate`` primitive on a single group, and the vectorized
``Experience.credibility_weighted`` over every group at once. (For variance-based
credibility, ``Buhlmann`` / ``BuhlmannStraub`` derive Z from the EPV and VHM
instead of a square-root rule.)

    pip install actuarialpy
    python credibility.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actuarialpy as ap  # noqa: E402
from _sample_data import sample_member_months  # noqa: E402

FULL_CREDIBILITY_MM = 12_000.0  # member-months for full credibility (illustrative)


def section(title: str) -> None:
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main() -> None:
    df = sample_member_months()
    exp = ap.Experience(
        df, expense="total_claims", revenue="premium", exposure="member_months"
    )

    book_lr = float(df["total_claims"].sum() / df["premium"].sum())
    section("book complement")
    print(f"book loss ratio (complement): {book_lr:.3f}")

    section("1. credibility_weighted_estimate on a single group")
    per_group = exp.by("group_id")
    g = per_group.iloc[0]
    n_mm = float(g["member_months"])
    z = min(1.0, math.sqrt(n_mm / FULL_CREDIBILITY_MM))
    observed = float(g["loss_ratio"])
    blended = ap.credibility_weighted_estimate(observed=observed, complement=book_lr, z=z)
    print(f"group {int(g['group_id'])}: observed LR {observed:.3f}, "
          f"member-months {n_mm:.0f}, Z {z:.2f} -> credibility-weighted LR {blended:.3f}")

    section("2. Experience.credibility_weighted across all groups (scalar Z)")
    blended_all = exp.credibility_weighted(
        "group_id", z=0.5, metric="loss_ratio", complement=book_lr
    )
    print(blended_all.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
