import pandas as pd
import pytest

from actuarialpy.reserving import (
    ibnr,
    lag_months,
    make_completion_triangle,
    validate_completion_factors,
)


def test_ibnr_identity():
    assert ibnr(1_000_000, 900_000) == 100_000
    out = ibnr(pd.Series([100.0, 200.0]), pd.Series([90.0, 150.0]))
    assert list(out) == [10.0, 50.0]


def test_lag_months():
    lag = lag_months(
        pd.Series(pd.to_datetime(["2026-01-01"])),
        pd.Series(pd.to_datetime(["2026-03-15"])),
    )
    assert int(lag.iloc[0]) == 2


def _triangle_frame():
    return pd.DataFrame({
        "origin": ["2026-01-01", "2026-01-01"],
        "valuation": ["2026-01-31", "2026-02-28"],
        "paid": [100, 150],
    })


def test_completion_triangle_cumulative_default():
    tri = make_completion_triangle(_triangle_frame(), origin_col="origin", valuation_col="valuation", amount_col="paid")
    p = pd.Period("2026-01", "M")
    assert tri.loc[p, 0] == 100
    assert tri.loc[p, 1] == 250  # cumulative: 100 + 150


def test_completion_triangle_incremental():
    tri = make_completion_triangle(
        _triangle_frame(), origin_col="origin", valuation_col="valuation", amount_col="paid", cumulative=False
    )
    p = pd.Period("2026-01", "M")
    assert tri.loc[p, 0] == 100
    assert tri.loc[p, 1] == 150


def test_validate_completion_factors():
    validate_completion_factors(pd.DataFrame({"completion_factor": [0.9, 0.95, 1.0]}))  # no raise
    with pytest.raises(ValueError):
        validate_completion_factors(pd.DataFrame({"completion_factor": [1.2]}))  # >1 invalid for divide
    validate_completion_factors(pd.DataFrame({"completion_factor": [1.1, 1.5]}), method="multiply")  # no raise
    with pytest.raises(ValueError):
        validate_completion_factors(pd.DataFrame({"completion_factor": [0.9]}), method="multiply")  # <1 invalid


# --------------------------------------------------------------------------- #
# chain-ladder completion-factor estimation
# --------------------------------------------------------------------------- #
def _cum_triangle():
    # cumulative paid triangle, lower-right unobserved (NaN)
    return pd.DataFrame(
        {0: [100.0, 200.0, 400.0], 1: [150.0, 300.0, float("nan")], 2: [165.0, float("nan"), float("nan")]},
        index=["A", "B", "C"],
    )


def test_chain_ladder_factors():
    from actuarialpy.reserving import ChainLadder

    cl = ChainLadder.fit(_cum_triangle())
    assert cl.age_to_age[0] == pytest.approx(1.5)    # (150+300)/(100+200)
    assert cl.age_to_age[1] == pytest.approx(1.1)    # 165/150
    assert cl.cdf[0] == pytest.approx(1.65)          # 1.5 * 1.1
    assert cl.cdf[1] == pytest.approx(1.1)
    assert cl.cdf[2] == pytest.approx(1.0)
    assert cl.completion_factors[0] == pytest.approx(1 / 1.65)
    assert cl.completion_factors[1] == pytest.approx(1 / 1.1)
    assert cl.completion_factors[2] == pytest.approx(1.0)


def test_completion_factors_helper():
    from actuarialpy.reserving import completion_factors

    cf = completion_factors(_cum_triangle())
    assert cf[0] == pytest.approx(1 / 1.65)
    assert (cf <= 1.0 + 1e-9).all()


def test_chain_ladder_tail():
    from actuarialpy.reserving import ChainLadder

    cl = ChainLadder.fit(_cum_triangle(), tail=1.05)
    assert cl.cdf[2] == pytest.approx(1.05)
    assert cl.cdf[1] == pytest.approx(1.1 * 1.05)
    assert cl.completion_factors[2] == pytest.approx(1 / 1.05)


def test_chain_ladder_simple_method():
    from actuarialpy.reserving import ChainLadder

    cl = ChainLadder.fit(_cum_triangle(), method="simple")
    assert cl.age_to_age[0] == pytest.approx(1.5)    # mean(150/100, 300/200)


def test_chain_ladder_project():
    from actuarialpy.reserving import ChainLadder

    tri = _cum_triangle()
    proj = ChainLadder.fit(tri).project(tri)
    assert proj.loc["A", "ultimate"] == pytest.approx(165.0)   # fully developed
    assert proj.loc["B", "ultimate"] == pytest.approx(330.0)   # 300 * 1.1
    assert proj.loc["C", "ultimate"] == pytest.approx(660.0)   # 400 * 1.65
    assert proj.loc["C", "ibnr"] == pytest.approx(260.0)
    assert proj["ultimate"].sum() == pytest.approx(1155.0)
    assert proj["ibnr"].sum() == pytest.approx(290.0)


def test_chain_ladder_validation():
    from actuarialpy.reserving import ChainLadder

    with pytest.raises(ValueError):
        ChainLadder.fit(_cum_triangle(), method="bogus")
    with pytest.raises(ValueError):
        ChainLadder.fit(_cum_triangle(), tail=0.9)
    with pytest.raises(ValueError):
        ChainLadder.fit(pd.DataFrame({0: [1.0, 2.0]}))  # only one lag column


def test_triangle_to_completion_factors_end_to_end():
    from actuarialpy.reserving import completion_factors, make_completion_triangle

    dev = pd.DataFrame({
        "incurred": ["2026-01-01", "2026-01-01", "2026-01-01", "2026-02-01", "2026-02-01", "2026-03-01"],
        "valuation": ["2026-01-31", "2026-02-28", "2026-03-31", "2026-02-28", "2026-03-31", "2026-03-31"],
        "paid": [60, 30, 10, 120, 40, 200],
    })
    tri = make_completion_triangle(dev, origin_col="incurred", valuation_col="valuation", amount_col="paid")
    cf = completion_factors(tri)
    assert (cf <= 1.0 + 1e-9).all()
    assert cf.iloc[-1] == pytest.approx(1.0)   # last observed lag fully emerged (tail = 1)


# --------------------------------------------------------------------------- #
# per-segment completion factors (chain_ladder_by / completion_factors_by)
# --------------------------------------------------------------------------- #
def _dev_two_lobs():
    # A develops slower than B (more IBNR)
    return pd.DataFrame({
        "lob": ["A"] * 6 + ["B"] * 6,
        "incurred": (["2026-01-01"] * 3 + ["2026-02-01"] * 2 + ["2026-03-01"]) * 2,
        "valuation": (["2026-01-31", "2026-02-28", "2026-03-31", "2026-02-28", "2026-03-31", "2026-03-31"]) * 2,
        "paid": [60, 30, 10, 120, 40, 200, 80, 15, 5, 150, 20, 260],
    })


def _dev_with_thin():
    thin = pd.DataFrame({"lob": ["C"], "incurred": ["2026-01-01"], "valuation": ["2026-01-31"], "paid": [100]})
    return pd.concat([_dev_two_lobs(), thin], ignore_index=True)


_BYARGS = dict(origin_col="incurred", valuation_col="valuation", amount_col="paid")


def test_chain_ladder_by_dict():
    from actuarialpy.reserving import chain_ladder_by

    pats = chain_ladder_by(_dev_two_lobs(), groupby="lob", **_BYARGS)
    assert set(pats) == {"A", "B"}
    assert pats["A"].completion_factors[0] < pats["B"].completion_factors[0]  # A slower
    assert pats["A"].completion_factors[0] == pytest.approx(0.648, abs=1e-3)


def test_completion_factors_by_tidy():
    from actuarialpy.reserving import completion_factors_by

    tidy = completion_factors_by(_dev_two_lobs(), groupby="lob", **_BYARGS)
    assert list(tidy.columns) == ["lob", "lag_month", "completion_factor"]
    assert len(tidy) == 6  # 2 LOBs x 3 lags
    a0 = tidy[(tidy["lob"] == "A") & (tidy["lag_month"] == 0)]["completion_factor"].iloc[0]
    assert a0 == pytest.approx(0.648, abs=1e-3)


def test_completion_factors_by_multi_column():
    from actuarialpy.reserving import completion_factors_by

    df = _dev_two_lobs()
    df["plan"] = "P1"
    tidy = completion_factors_by(df, groupby=["lob", "plan"], **_BYARGS)
    assert list(tidy.columns) == ["lob", "plan", "lag_month", "completion_factor"]
    assert set(tidy["lob"]) == {"A", "B"}


def test_chain_ladder_by_raise_default():
    from actuarialpy.reserving import chain_ladder_by

    with pytest.raises(ValueError, match="'C'"):
        chain_ladder_by(_dev_with_thin(), groupby="lob", **_BYARGS)


def test_chain_ladder_by_skip_warns():
    from actuarialpy.reserving import InsufficientDataWarning, chain_ladder_by

    with pytest.warns(InsufficientDataWarning, match="C"):
        pats = chain_ladder_by(_dev_with_thin(), groupby="lob", on_insufficient="skip", **_BYARGS)
    assert set(pats) == {"A", "B"}  # thin segment dropped


def test_chain_ladder_by_aggregate():
    import warnings as _w

    from actuarialpy.reserving import ChainLadder, chain_ladder_by, make_completion_triangle

    with _w.catch_warnings():
        _w.simplefilter("ignore")
        pats = chain_ladder_by(_dev_with_thin(), groupby="lob", on_insufficient="aggregate", **_BYARGS)
    assert set(pats) == {"A", "B", "C"}
    agg = ChainLadder.fit(make_completion_triangle(_dev_with_thin(), **_BYARGS))
    assert list(pats["C"].completion_factors.round(6)) == list(agg.completion_factors.round(6))


def test_chain_ladder_by_warn_suppressed():
    import warnings as _w

    from actuarialpy.reserving import InsufficientDataWarning, chain_ladder_by

    with _w.catch_warnings(record=True) as rec:
        _w.simplefilter("always")
        pats = chain_ladder_by(_dev_with_thin(), groupby="lob", on_insufficient="skip", warn=False, **_BYARGS)
    assert not any(isinstance(r.message, InsufficientDataWarning) for r in rec)
    assert set(pats) == {"A", "B"}


def test_chain_ladder_by_bad_policy():
    from actuarialpy.reserving import chain_ladder_by

    with pytest.raises(ValueError, match="on_insufficient"):
        chain_ladder_by(_dev_two_lobs(), groupby="lob", on_insufficient="bogus", **_BYARGS)
