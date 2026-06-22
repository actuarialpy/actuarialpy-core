import pandas as pd

from actuarialpy.banding import assign_band, summarize_by_band
from actuarialpy.concentration import (
    concentration_curve,
    concentration_summary,
    top_n_share,
)
from actuarialpy.experience import summarize_experience
from actuarialpy.margins import add_margin
from actuarialpy.metrics import permissible_loss_ratio
from actuarialpy.pooling import (
    excess_over_threshold,
    flag_large_losses,
    large_loss_summary,
    pool_losses,
)


# --------------------------------------------------------------------------- #
# Generalized default ratio name
# --------------------------------------------------------------------------- #
def test_default_ratio_is_loss_ratio():
    df = pd.DataFrame({
        "line": ["A", "A"],
        "losses": [50, 50],
        "premium": [100, 100],
    })
    out = summarize_experience(df, groupby="line", expense_cols="losses", revenue_cols="premium")
    assert "loss_ratio" in out.columns
    assert "mlr" not in out.columns
    assert "expense_revenue_ratio" not in out.columns
    assert out.iloc[0]["loss_ratio"] == 0.5


# --------------------------------------------------------------------------- #
# Banding
# --------------------------------------------------------------------------- #
def banding_df():
    return pd.DataFrame({
        "subs": [10, 50, 60, 75, 100, 200],
        "claims": [10, 40, 80, 20, 150, 180],
        "premium": [100, 100, 100, 100, 200, 200],
    })


def test_assign_band_left_closed():
    out = assign_band(banding_df(), "subs", [0, 51, 76, 151, float("inf")])
    bands = list(out["band"])
    assert bands == ["0-50", "0-50", "51-75", "51-75", "76-150", "151+"]


def test_summarize_by_band():
    out = summarize_by_band(
        banding_df(),
        "subs",
        [0, 51, 76, 151, float("inf")],
        expense_cols="claims",
        revenue_cols="premium",
    )
    assert list(out["band"]) == ["0-50", "51-75", "76-150", "151+"]
    by_band = out.set_index("band")
    assert by_band.loc["0-50", "total_expense"] == 50
    assert by_band.loc["0-50", "loss_ratio"] == 0.25
    assert by_band.loc["76-150", "loss_ratio"] == 0.75
    assert by_band.loc["151+", "loss_ratio"] == 0.9


# --------------------------------------------------------------------------- #
# Concentration
# --------------------------------------------------------------------------- #
def concentration_df():
    # G1 has two rows to exercise the per-entity aggregation.
    return pd.DataFrame({
        "group_id": ["G1", "G1", "G2", "G3", "G4"],
        "mm": [60, 40, 50, 30, 20],
        "premium": [600, 400, 400, 300, 200],
    })


def test_concentration_curve():
    out = concentration_curve(
        concentration_df(),
        by_col="group_id",
        rank_col="mm",
        value_cols=["mm", "premium"],
        ns=(1, 2, 3, 4),
    )
    by_n = out.set_index("n")
    assert by_n.loc[1, "mm"] == 100      # G1
    assert by_n.loc[1, "premium"] == 1000
    assert by_n.loc[1, "share"] == 0.5   # 100 / 200
    assert by_n.loc[2, "mm"] == 150
    assert by_n.loc[2, "share"] == 0.75
    assert by_n.loc[4, "share"] == 1.0


def test_top_n_share_and_summary():
    df = concentration_df()
    assert top_n_share(df, by_col="group_id", amount_col="mm", n=1) == 0.5
    assert top_n_share(df, by_col="group_id", amount_col="mm", n=2) == 0.75
    summary = concentration_summary(df, by_col="group_id", amount_col="mm", ns=(1, 3))
    assert list(summary["n"]) == [1, 3]


def test_concentration_n_exceeds_entity_count():
    df = concentration_df()  # only 4 entities
    out = concentration_curve(df, by_col="group_id", rank_col="mm", ns=(10,))
    assert out.iloc[0]["entities"] == 4
    assert out.iloc[0]["share"] == 1.0


# --------------------------------------------------------------------------- #
# Margins
# --------------------------------------------------------------------------- #
def test_add_margin_with_ratio_and_per_exposure():
    df = pd.DataFrame({
        "premium": [1000],
        "medical": [700],
        "retention": [100],
        "commission": [50],
        "member_months": [100],
    })
    out = add_margin(
        df,
        premium_col="premium",
        expense_cols=["medical", "retention", "commission"],
        ratio_col="margin_pct",
        exposure_col="member_months",
        per_exposure_col="margin_pmpm",
    )
    row = out.iloc[0]
    assert row["margin"] == 150
    assert row["margin_pct"] == 0.15
    assert row["margin_pmpm"] == 1.5


# --------------------------------------------------------------------------- #
# Pooling / large losses
# --------------------------------------------------------------------------- #
def claims_df():
    return pd.DataFrame({
        "claimant_id": ["C1", "C2", "C3", "C4", "C5"],
        "loss": [30000, 150000, 80000, 250000, 5000],
    })


def test_pool_losses_split():
    out = pool_losses(claims_df(), "loss", 100000)
    by_id = out.set_index("claimant_id")
    assert by_id.loc["C4", "pooled_loss"] == 100000
    assert by_id.loc["C4", "excess_loss"] == 150000
    assert by_id.loc["C1", "excess_loss"] == 0
    assert out["pooled_loss"].sum() == 315000
    assert out["excess_loss"].sum() == 200000


def test_flag_large_losses():
    out = flag_large_losses(claims_df(), "loss", 100000)
    assert int(out["is_large"].sum()) == 2


def test_large_loss_summary():
    out = large_loss_summary(claims_df(), "loss", 100000, entity_col="claimant_id")
    row = out.iloc[0]
    assert row["large_count"] == 2
    assert row["large_total"] == 400000
    assert row["large_mean"] == 200000
    assert row["large_entities"] == 2
    assert abs(row["share_of_total"] - 400000 / 515000) < 1e-9


def test_excess_over_threshold_handoff():
    out = excess_over_threshold(claims_df(), "loss", 100000, keep_cols="claimant_id")
    assert list(out["claimant_id"]) == ["C2", "C4"]
    assert list(out["excess"]) == [50000, 150000]


# --------------------------------------------------------------------------- #
# Permissible / zero-margin loss ratio
# --------------------------------------------------------------------------- #
def test_permissible_loss_ratio():
    assert abs(permissible_loss_ratio(0.136) - 0.864) < 1e-9
    assert abs(permissible_loss_ratio(0.136, 0.05) - 0.814) < 1e-9
