import pandas as pd
import pytest

from actuarialpy import (
    Experience,
    add_margin,
    excess_over_threshold,
    permissible_loss_ratio,
    pool_losses,
    summarize_by_band,
)


def frame():
    return pd.DataFrame({
        "group_id": ["G1", "G1", "G2", "G2", "G3", "G3"],
        "member_id": ["M1", "M2", "M3", "M4", "M5", "M6"],
        "subscribers": [3, 3, 12, 12, 30, 30],
        "claims": [100, 50, 400, 200, 900, 300],
        "premium": [200, 200, 600, 600, 1000, 1000],
        "member_months": [1, 1, 1, 1, 1, 1],
        "effective_date": pd.to_datetime([
            "2020-01-01", "2020-01-01",   # G1 long-tenured -> active
            "2026-03-01", "2026-03-01",   # G2 recent -> first_year
            "2022-01-01", "2022-01-01",   # G3 termed below
        ]),
        "termination_date": pd.to_datetime([None, None, None, None, "2025-06-01", "2025-06-01"]),
    })


# --------------------------------------------------------------------------- #
# Fix: default ratio name is loss_ratio again
# --------------------------------------------------------------------------- #
def test_default_ratio_is_loss_ratio():
    out = Experience(frame(), expense="claims", revenue="premium").by("group_id")
    assert "loss_ratio" in out.columns
    assert "expense_revenue_ratio" not in out.columns


# --------------------------------------------------------------------------- #
# permissible_loss_ratio
# --------------------------------------------------------------------------- #
def test_permissible_loss_ratio():
    assert permissible_loss_ratio(0.136) == pytest.approx(0.864)
    assert permissible_loss_ratio(0.12, 0.04) == pytest.approx(0.84)


# --------------------------------------------------------------------------- #
# Banding: free function and Experience.by_band agree
# --------------------------------------------------------------------------- #
def test_banding_free_and_method():
    df = frame()
    bands = [0, 5, 25, float("inf")]
    labels = ["1-4", "5-24", "25+"]
    direct = summarize_by_band(
        df, "subscribers", bands, labels=labels,
        expense_cols="claims", revenue_cols="premium", exposure_cols="member_months",
    )
    exp = Experience(df, expense="claims", revenue="premium", exposure="member_months")
    via = exp.by_band("subscribers", bands, labels=labels)
    pd.testing.assert_frame_equal(direct, via)
    by_band = via.set_index("band")
    assert by_band.loc["1-4", "total_expense"] == 150  # G1: 100 + 50
    assert by_band.loc["1-4", "loss_ratio"] == pytest.approx(150 / 400)


# --------------------------------------------------------------------------- #
# Margins: free function and Experience.margin
# --------------------------------------------------------------------------- #
def test_margin_method_and_free():
    df = frame()
    exp = Experience(df, expense="claims", revenue="premium", exposure="member_months")
    m = exp.margin("group_id", per_exposure_col="margin_pmpm")
    g1 = m[m["group_id"] == "G1"].iloc[0]
    assert g1["margin"] == 250                       # 400 revenue - 150 expense
    assert g1["margin_ratio"] == pytest.approx(0.625)
    assert g1["margin_pmpm"] == pytest.approx(125)   # 250 / 2 member-months

    totals = df.groupby("group_id", as_index=False).agg(premium=("premium", "sum"), claims=("claims", "sum"))
    out = add_margin(totals, premium_col="premium", expense_cols="claims", ratio_col="mp")
    assert out[out["group_id"] == "G1"].iloc[0]["margin"] == 250


# --------------------------------------------------------------------------- #
# Pooling: free functions and Experience.pool_claimants
# --------------------------------------------------------------------------- #
def test_pooling_free_and_method():
    claimants = pd.DataFrame({"member_id": ["A", "B", "C"], "loss": [100, 5000, 20000]})
    pooled = pool_losses(claimants, "loss", 10000)
    assert list(pooled["pooled_loss"]) == [100, 5000, 10000]
    assert list(pooled["excess_loss"]) == [0, 0, 10000]
    excess = excess_over_threshold(claimants, "loss", 10000, keep_cols="member_id")
    assert list(excess["member_id"]) == ["C"]
    assert list(excess["excess"]) == [10000]

    exp = Experience(frame(), expense="claims", revenue="premium")
    pc = exp.pool_claimants("member_id", 250)
    by_m = pc.set_index("member_id")
    assert by_m.loc["M5", "pooled_loss"] == 250   # M5 total 900 capped at 250
    assert by_m.loc["M5", "excess_loss"] == 650
    assert by_m.loc["M1", "excess_loss"] == 0     # M1 total 100, below cap


# --------------------------------------------------------------------------- #
# Lifecycle integration: Experience.with_status -> by_status
# --------------------------------------------------------------------------- #
def test_with_status_and_by_status():
    exp = Experience(frame(), expense="claims", revenue="premium", exposure="member_months")
    staged = exp.with_status(
        effective_col="effective_date", termination_col="termination_date",
        as_of="2026-12-31", first_year_months=12,
    )
    assert isinstance(staged, Experience)
    status = staged.data.drop_duplicates("group_id").set_index("group_id")["status"]
    assert status["G1"] == "active"
    assert status["G2"] == "first_year"
    assert status["G3"] == "termed"
    by_status = staged.by_status("status", entity_col="group_id")
    assert set(by_status["status"]) == {"active", "first_year", "termed"}


# --------------------------------------------------------------------------- #
# Credibility integration: Experience.credibility_weighted
# --------------------------------------------------------------------------- #
def test_credibility_weighted():
    exp = Experience(frame(), expense="claims", revenue="premium")
    out = exp.credibility_weighted("group_id", z=0.5)
    book = 1950 / 3600  # total claims / total premium
    g1 = out[out["group_id"] == "G1"].iloc[0]
    assert g1["credibility_weighted_loss_ratio"] == pytest.approx(0.5 * 0.375 + 0.5 * book)
