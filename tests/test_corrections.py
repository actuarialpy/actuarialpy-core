"""Tests covering the 0.5.0 corrections."""

import numpy as np
import pandas as pd
import pytest

import actuarialpy as ap
from actuarialpy.columns import as_list, per_exposure_name
from actuarialpy.completion import make_completion_triangle
from actuarialpy.metrics import combined_ratio, loss_ratio, pmpm
from actuarialpy.rolling import rolling_summary


def test_scalar_return_types_are_native_floats():
    assert isinstance(loss_ratio(85, 100), float)
    assert isinstance(combined_ratio(70, 20, 100), float)
    assert loss_ratio(85, 100) == 0.85
    assert combined_ratio(70, 20, 100) == 0.90


def test_series_in_series_out_preserves_index():
    claims = pd.Series([100, 200], index=[5, 9], name="claims")
    premium = pd.Series([200, 400], index=[5, 9])
    result = loss_ratio(claims, premium)
    assert isinstance(result, pd.Series)
    assert result.index.tolist() == [5, 9]
    assert result.tolist() == [0.5, 0.5]


def test_combined_ratio_series_and_list():
    losses = pd.Series([70, 70], index=[1, 2])
    expenses = pd.Series([20, 20], index=[1, 2])
    out = combined_ratio(losses, expenses, pd.Series([100, 100], index=[1, 2]))
    assert isinstance(out, pd.Series)
    assert out.tolist() == [0.9, 0.9]
    # Lists must be summed element-wise, not concatenated.
    arr = combined_ratio([70, 70], [20, 20], [100, 100])
    assert np.allclose(arr, [0.9, 0.9])


def test_zero_exposure_pmpm_is_nan():
    assert np.isnan(pmpm(1_000, 0))
    s = pmpm(pd.Series([1_000, 500]), pd.Series([0, 10]))
    assert np.isnan(s.iloc[0])
    assert s.iloc[1] == 50


def test_as_list_set_is_deterministic():
    assert as_list({"b", "a", "c"}) == ["a", "b", "c"]


def test_per_exposure_name_helper():
    assert per_exposure_name("inpatient", "member_months") == "inpatient_pmpm"
    assert per_exposure_name("inpatient", "subscriber_months") == "inpatient_pspm"
    assert per_exposure_name("inpatient", "life_years") == "inpatient_per_life_years"


def test_completion_triangle_cumulative():
    # Incremental amounts at each lag for one origin month.
    df = pd.DataFrame(
        {
            "origin": ["2026-01-01", "2026-01-01", "2026-01-01"],
            "valuation": ["2026-01-31", "2026-02-28", "2026-03-31"],
            "paid": [100, 50, 25],  # incremental
        }
    )
    incremental = make_completion_triangle(
        df, origin_col="origin", valuation_col="valuation", amount_col="paid"
    )
    cumulative = make_completion_triangle(
        df, origin_col="origin", valuation_col="valuation", amount_col="paid", cumulative=True
    )
    origin = pd.Period("2026-01", "M")
    assert incremental.loc[origin, 2] == 25
    assert cumulative.loc[origin, 0] == 100
    assert cumulative.loc[origin, 1] == 150
    assert cumulative.loc[origin, 2] == 175


def _gapped_monthly():
    # February is missing entirely.
    return pd.DataFrame(
        {
            "month": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-04-01", "2026-05-01"]),
            "claims": [100, 300, 400, 500],
            "premium": [200, 200, 200, 200],
            "member_months": [10, 10, 10, 10],
        }
    )


def test_rolling_is_calendar_aware_with_gaps():
    out = rolling_summary(
        _gapped_monthly(),
        date_col="month",
        window=3,
        freq="MS",
        expense_cols="claims",
        revenue_cols="premium",
        exposure_cols="member_months",
    )
    # First complete 3-calendar-month window ends in March and starts in January,
    # spanning exactly Jan, Feb (filled with zero), Mar -- not stretching to April.
    first = out.iloc[0]
    assert first["period_end"] == pd.Timestamp("2026-03-01")
    assert first["period_start"] == pd.Timestamp("2026-01-01")
    # Jan claims (100) + Feb (filled 0) + Mar (300) = 400.
    assert first["total_expense"] == 400
    # March, April, May each anchor a complete window.
    assert out["period_end"].tolist() == [
        pd.Timestamp("2026-03-01"),
        pd.Timestamp("2026-04-01"),
        pd.Timestamp("2026-05-01"),
    ]


def test_rolling_requires_freq_for_gapped_data():
    with pytest.raises(ValueError):
        rolling_summary(
            _gapped_monthly(),
            date_col="month",
            window=3,
            expense_cols="claims",
            revenue_cols="premium",
            exposure_cols="member_months",
        )


def test_top_level_imports_available():
    for name in [
        "summarize_experience",
        "rolling_summary",
        "trend_summary",
        "complete_claims",
        "component_driver_analysis",
        "cohort_summary",
        "forecast_experience",
        "to_excel_report",
        "relative_change",
    ]:
        assert hasattr(ap, name), f"{name} should be importable from actuarialpy"
