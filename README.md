# ActuarialPy

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

An experience-centered Python toolkit for actuarial analysis on tabular data.

---

## Overview

ActuarialPy turns a claims / exposure / premium table into a set of standard
actuarial analyses with very little ceremony. You define the actuarial *roles* of
your columns once — what is expense, revenue, exposure, and the date — and then ask
the resulting `Experience` object for summaries, rolling views, trends, driver
analyses, actual-versus-expected, concentration reviews, cohort/duration tables,
and more. The same role assignments are reused across every analysis, so you never
re-specify which column is premium or how to compute a loss ratio.

Alongside the `Experience` object, every calculation is also available as a plain
function (loss ratios, PMPM/PSPM/PEPM, trend factors, chain-ladder completion
factors, credibility formulas), so the library works equally well for one-off
calculations and for building larger pipelines.

It is deterministic and pandas-native: the only dependencies are `numpy` and
`pandas`, and outputs are ordinary DataFrames and Series you can inspect, join, and
export.

## Highlights

- **The `Experience` object** — assign column roles once, then produce grouped
  summaries, rolling windows, trends, component drivers, actual-vs-expected,
  claimant concentration, cohort/duration tables, size bands, and lifecycle views.
- **Ratios and per-exposure metrics** — loss ratio, medical loss ratio, combined
  and expense ratios, pure premium, frequency, severity, and PMPM / PSPM / PEPM /
  generic per-exposure metrics.
- **Reserving** — development triangles and chain-ladder completion factors,
  ultimates, and IBNR, overall or per segment, with completeness validation.
- **Credibility** — greatest-accuracy credibility (Bühlmann and Bühlmann-Straub)
  and direct credibility-weighting of any estimate.
- **Trend and forecasting** — annualized trend, midpoint trend factors, projecting
  values forward, period-over-period comparisons, and rate-based forecasts.
- **Lifecycle and exposure** — in-force determination, earned exposure, tenure,
  and active / first-year / termed status.
- **Pooling, banding, and margins** — pooling points and excess losses, size
  banding, and underwriting margins.
- **Reporting** — write a dictionary of analysis views to a multi-sheet workbook.

## Installation

```bash
pip install actuarialpy
```

From a source checkout:

```bash
pip install -e .
```

Requires Python `>=3.10`; depends only on `numpy` and `pandas`.

## Package structure

```text
actuarialpy/
├── frame.py         # the Experience object (role-aware analysis facade)
├── experience.py    # grouped experience summaries and multi-view summaries
├── rolling.py       # rolling-window experience summaries
├── trend.py         # trend factors, projections, period-over-period comparisons
├── forecast.py      # rate-based forecasting and actual-vs-forecast
├── components.py    # component / driver decompositions
├── contribution.py  # share-of-total and contribution-to-change
├── expected.py      # actual-versus-expected summaries
├── claimants.py     # large-claimant flags and concentration
├── pooling.py       # pooling points and excess losses
├── cohorts.py       # cohort and duration summaries
├── lifecycle.py     # in-force, earned exposure, tenure, status
├── banding.py       # size banding and banded summaries
├── margins.py       # underwriting margins
├── metrics.py       # ratios and per-exposure metrics
├── credibility.py   # Bühlmann / Bühlmann-Straub credibility
├── reserving.py     # triangles, chain ladder, completion factors, IBNR
├── periods.py       # period / duration column helpers
├── profiles.py      # naming profiles (e.g. health vs. P&C terminology)
└── reporting.py     # multi-sheet workbook export
```

## The Experience object

Define the roles of your dataset once:

```python
import actuarialpy as ap

exp = ap.Experience(
    claims,                      # a pandas DataFrame
    expense="total_claims",      # the loss / claim amount column(s)
    revenue="premium",           # the premium / revenue column(s)
    exposure="member_months",    # the exposure column(s)
    date="incurred_month",       # the time column
    profile="health",            # naming profile (health -> MLR, PMPM terminology)
)
```

Then reuse it across analyses:

```python
# grouped experience summary (totals + loss ratio / MLR by group)
summary = exp.by(["group_id", "product_code"])

# trailing-12-month rolling view per product
rolling = exp.rolling(window=12, groupby="product_code")

# period-over-period trend
trend = exp.trend(
    prior_start="2025-01-01", prior_end="2025-12-31",
    current_start="2026-01-01", current_end="2026-12-31",
    groupby="product_code",
)

# several named cuts at once
views = exp.views({"overall": None, "by_group": "group_id", "by_product": "product_code"})
```

`Experience` is immutable-friendly: `exp.filter(query="product_code == 'A'")` and
`exp.with_roles(...)` return new objects without mutating the original.

### Experience methods

| Method | Produces |
| --- | --- |
| `by(groupby)` | grouped totals and ratios |
| `views(views)` | a dict of named grouped summaries |
| `rolling(window, groupby)` | rolling-window summaries |
| `trend(prior/current windows, groupby)` | period-over-period trend |
| `components(component_cols, ...)` / `component_summary(...)` | component / driver breakdowns |
| `actual_vs_expected(expected, actual, ...)` | actual-versus-expected with variances |
| `claimants(...)` / `top_claimants(...)` / `claimant_concentration(...)` | large-claimant and concentration views |
| `pool_claimants(claimant_col, pooling_point)` | pooled vs. excess by claimant |
| `cohort(...)` / `duration(...)` | cohort and duration summaries |
| `by_band(value_col, bands)` | banded summaries |
| `with_status(...)` / `by_status(...)` | lifecycle status assignment and summary |
| `margin(...)` | underwriting margins |
| `credibility_weighted(groupby, z, metric)` | credibility-blended estimates by group |
| `filter(...)` / `with_roles(...)` | derive a new Experience |

## Reserving

Build a development triangle from transactional data, fit a chain ladder, and read
off ultimates and IBNR. Origin and development (lag) periods are derived for you.

```python
from actuarialpy import make_completion_triangle, ChainLadder, completion_factors

triangle = make_completion_triangle(
    claims,
    origin_col="incurred_month",
    valuation_col="paid_month",
    amount_col="paid",
    cumulative=True,
)

cl = ChainLadder.fit(triangle, method="volume", tail=1.0)
projection = cl.project(triangle)
# projection columns: latest_lag, latest, development_factor, ultimate, ibnr

# or just the completion factors (1 / cumulative development factor)
factors = completion_factors(triangle, method="volume", tail=1.0)
```

`ChainLadder.fit` exposes `age_to_age`, `cdf`, `completion_factors`, `tail`, and
`method`. Segment-level reserving is available without manually splitting data:

```python
from actuarialpy import chain_ladder_by, completion_factors_by

per_segment = chain_ladder_by(
    claims, groupby="line_of_business",
    origin_col="incurred_month", valuation_col="paid_month", amount_col="paid",
    on_insufficient="skip",   # "raise", "skip", or "aggregate"
)
```

Supporting helpers: `lag_months(incurred, valuation)`, `ibnr(completed, paid)`, and
`validate_completion_factors(...)` (which checks a factor column is monotone and in
range and warns on `InsufficientDataWarning`).

## Credibility

Greatest-accuracy credibility, either fit empirically from per-risk observations or
constructed from known structural parameters.

```python
from actuarialpy import Buhlmann, BuhlmannStraub, credibility_weighted_estimate

# Bühlmann: rows are risks, columns are observed periods
data = [[10, 12, 9, 11], [20, 18, 22, 19], [5, 6, 4, 7]]
model = Buhlmann.fit(data)
print(model.z, model.k)               # credibility factor and credibility constant
print(model.premium(risk_mean=11.0))  # credibility-weighted premium for a risk

# Bühlmann-Straub: unequal exposures via weights
ws = BuhlmannStraub.fit(data, weights=[[1, 1, 1, 1], [2, 2, 2, 2], [1, 1, 1, 1]])
print(ws.z(weight=6), ws.premium(risk_mean=11.0, weight=6))

# or blend any observed estimate with a complement directly
est = credibility_weighted_estimate(observed=0.82, complement=0.75, z=0.6)
```

You can also construct the models directly from parameters —
`Buhlmann(overall_mean, epv, vhm, n_obs)` and
`BuhlmannStraub(overall_mean, epv, vhm, weights)` — when EPV and VHM are already
known.

## Trend and forecasting

```python
from actuarialpy import trend_factor, annualized_trend, project_forward, trend_summary

trend_factor(0.06, months=18)            # (1 + 0.06) ** (18/12)
project_forward(1000.0, 0.06, months=18) # trend a value forward 18 months
annualized_trend(current=1.1, prior=1.0, months_between=12)

# trend a metric between two windows of a transactional frame
summary = trend_summary(
    claims, date_col="incurred_month",
    prior_start="2025-01-01", prior_end="2025-12-31",
    current_start="2026-01-01", current_end="2026-12-31",
    amount_col="paid", exposure_col="member_months", groupby="product_code",
)
```

Rate-based forecasting lives in the forecast module: `forecast_experience(...)`
applies a trended per-exposure rate to projected exposure, with
`forecast_from_rate(...)`, `expected_from_rate(...)`, and
`compare_actual_to_expected(...)` as supporting helpers.

## Ratios and per-exposure metrics

All of these accept scalars, NumPy arrays, or pandas Series, and divide safely
(returning NaN rather than raising on a zero denominator):

| Function | Definition |
| --- | --- |
| `loss_ratio(losses, revenue)` | losses ÷ revenue |
| `medical_loss_ratio(claims, premium)` | claims ÷ premium |
| `expense_ratio(expenses, revenue)` | expenses ÷ revenue |
| `combined_ratio(losses, expenses, revenue)` | (losses + expenses) ÷ revenue |
| `pure_premium(losses, exposure)` | losses ÷ exposure |
| `frequency(claim_count, exposure)` | claims ÷ exposure |
| `severity(losses, claim_count)` | losses ÷ claim count |
| `pmpm` / `pspm` / `pepm(amount, months)` | per-member / -subscriber / -employee per month |
| `per_exposure(amount, exposure)` | generic per-exposure rate |
| `permissible_loss_ratio(expense_ratio, profit_provision)` | 1 − expense ratio − profit |
| `required_revenue(expense, target_ratio)` | expense ÷ target ratio |
| `indicated_change(required, current)` | required ÷ current − 1 |
| `actual_to_expected(actual, expected)` | actual ÷ expected |

## Lifecycle, pooling, banding, and margins

- **Lifecycle** (`lifecycle`): `is_in_force(...)`, `earned_exposure(...)`,
  `add_months_in_force(...)`, `add_tenure(...)`, and `derive_status(...)` (which
  labels rows `STATUS_ACTIVE` / `STATUS_FIRST_YEAR` / `STATUS_TERMED`).
- **Pooling** (`pooling`): `pool_losses(df, loss_col, pooling_point)` splits each
  loss into pooled and excess amounts; `excess_over_threshold(...)` isolates the
  excess layer.
- **Banding** (`banding`): `assign_band(df, value_col, bands)` and
  `summarize_by_band(...)` for size-band experience.
- **Margins** (`margins`): `add_margin(...)` / `margin(...)` / `margin_ratio(...)`.
- **Contribution** (`contribution`): `share_of_total(...)`,
  `contribution_to_change(...)`, and `top_contributors(...)`.

## Reporting

Write a set of named analysis views to a multi-sheet Excel workbook:

```python
from actuarialpy.reporting import to_excel_report

views = exp.views({"overall": None, "by_group": "group_id"})
to_excel_report(views, "experience_report.xlsx")
```

## The ActuarialPy ecosystem

ActuarialPy is the deterministic, experience-and-data layer of a small family of
actuarial packages. It is standalone (only `numpy` and `pandas`) and focuses on
turning real data into summaries, triangles, trends, and credibility-weighted
estimates. Three companion packages cover the distributional and simulation side
and interoperate through a simple `.sample()` / `.mean()` interface:

- **`lossmodels`** — frequency and severity distributions, aggregate
  (collective-risk) loss models, coverage modifications, and model fitting.
- **`risksim`** — portfolio loss simulation and aggregate reinsurance program
  evaluation.
- **`extremeloss`** — extreme value theory: tail fitting (peaks-over-threshold /
  GPD, block maxima / GEV), tail risk measures, and threshold diagnostics.

## Testing

```bash
pytest -q
```

## License

MIT License