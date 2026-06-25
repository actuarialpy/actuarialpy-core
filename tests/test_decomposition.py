"""Tests for frequency-severity summary and PMPM trend decomposition."""

import numpy as np
import pandas as pd
import pytest

from actuarialpy import decompose_pmpm_trend, frequency_severity_summary


def _book(freq_per_mm, sev, mm=1000, n_months=12, **extra):
    rows = []
    for i in range(n_months):
        cnt = freq_per_mm * mm
        row = dict(month=i, claim_count=cnt, claims=cnt * sev, member_months=mm)
        row.update(extra)
        rows.append(row)
    return pd.DataFrame(rows)


def _fs(df, **kw):
    return frequency_severity_summary(df, count_col="claim_count", loss_col="claims",
                                      exposure_col="member_months", **kw)


def _dec(prior, current, **kw):
    return decompose_pmpm_trend(prior, current, count_col="claim_count", loss_col="claims",
                                exposure_col="member_months", **kw)


def test_pmpm_equals_frequency_times_severity():
    row = _fs(_book(0.40, 250.0)).iloc[0]
    assert row["pmpm"] == pytest.approx(row["frequency"] * row["severity"])
    assert row["pmpm"] == pytest.approx(100.0)


def test_util_per_1000_annualized():
    row = _fs(_book(0.40, 250.0)).iloc[0]
    assert row["util_per_1000"] == pytest.approx(row["frequency"] * 12 * 1000)


def test_summary_groupby():
    df = pd.concat([_book(0.40, 250.0, plan="A"), _book(0.30, 300.0, plan="B")], ignore_index=True)
    out = _fs(df, groupby="plan")
    assert sorted(out["plan"]) == ["A", "B"]
    assert (out["pmpm"] == out["frequency"] * out["severity"]).all()


def test_multiplicative_decomposition_exact():
    d = _dec(_book(0.40, 250.0), _book(0.42, 262.5)).iloc[0]
    assert d["util_trend"] * d["cost_trend"] == pytest.approx(d["pmpm_trend"])
    assert d["util_trend"] == pytest.approx(1.05)
    assert d["cost_trend"] == pytest.approx(1.05)
    assert d["pmpm_trend"] == pytest.approx(1.1025)


def test_additive_decomposition_exact():
    d = _dec(_book(0.40, 250.0), _book(0.42, 262.5)).iloc[0]
    assert d["util_effect"] + d["cost_effect"] == pytest.approx(d["pmpm_change"])
    assert d["pmpm_change"] == pytest.approx(10.25)


def test_pure_utilization_change():
    d = _dec(_book(0.40, 250.0), _book(0.48, 250.0)).iloc[0]   # only frequency moves
    assert d["cost_trend"] == pytest.approx(1.0)
    assert d["util_trend"] == pytest.approx(1.2)
    assert d["cost_effect"] == pytest.approx(0.0)


def test_pure_cost_change():
    d = _dec(_book(0.40, 250.0), _book(0.40, 275.0)).iloc[0]   # only severity moves
    assert d["util_trend"] == pytest.approx(1.0)
    assert d["cost_trend"] == pytest.approx(1.1)
    assert d["util_effect"] == pytest.approx(0.0)


def test_decompose_grouped_outer_join():
    pri = pd.concat([_book(0.40, 250.0, plan="A"), _book(0.30, 300.0, plan="B")], ignore_index=True)
    cur = pd.concat([_book(0.42, 262.5, plan="A"), _book(0.30, 300.0, plan="C")], ignore_index=True)
    out = _dec(pri, cur, on="plan")
    assert set(out["plan"]) == {"A", "B", "C"}   # outer join keeps one-sided plans
    a = out[out["plan"] == "A"].iloc[0]
    assert a["pmpm_trend"] == pytest.approx(1.1025)


def test_output_leads_with_pmpm_and_trends():
    cols = list(_dec(_book(0.40, 250.0), _book(0.42, 262.5)).columns)
    assert cols[:5] == ["pmpm_prior", "pmpm_current", "pmpm_trend", "util_trend", "cost_trend"]
