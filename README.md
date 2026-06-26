# ActuarialPy

Standard actuarial analyses on your real data — loss ratios and PMPM, development
triangles and IBNR, trend, credibility, seasonality, and utilization/unit-cost
decomposition — computed straight from the long, transactional tables you already have.
Deterministic and pandas-native: the only dependencies are `numpy` and `pandas`, and
every result is an ordinary DataFrame or Series you can inspect, join, and export.

## Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The `Experience` object](#the-experience-object)
- [Ratios and per-exposure metrics](#ratios-and-per-exposure-metrics)
- [Reserving](#reserving)
- [Trend and forecasting](#trend-and-forecasting)
- [Utilization and PMPM decomposition](#utilization-and-pmpm-decomposition)
- [Seasonality and working days](#seasonality-and-working-days)
- [Adjustments and restatement](#adjustments-and-restatement)
- [Actual versus forecast](#actual-versus-forecast)
- [Credibility](#credibility)
- [Lifecycle, pooling, banding, margins](#lifecycle-pooling-banding-margins)
- [Reporting](#reporting)
- [The ActuarialPy ecosystem](#the-actuarialpy-ecosystem)

## Overview

ActuarialPy is a calculation library. Its job is the arithmetic that has to be right —
loss ratios, per-exposure rates, chain-ladder development, credibility blends, seasonal
factors, the LMDI trend split — applied to ordinary claims, eligibility, and premium data.
It does not own your data prep or your filed methodology; you bring the table, choose the
method, and the library computes.

There are two ways in, and they layer:

- **Free functions** — `loss_ratio`, `pmpm`, `severity`, `trend_factor`, `fit_trend`,
  `seasonality_factors`, `decompose_pmpm_trend`, the credibility models, and the rest.
  Each takes scalars, NumPy arrays, or pandas Series and returns the same. Use them on any
  frame, at any grain you've aggregated to.
- **The `Experience` object** — when you'll run several analyses at one grain, bind the
  column roles once (what's expense, revenue, exposure, date) and reuse them across grouped
  summaries, rolling windows, trends, completion, seasonality, and more.

## Installation

```bash
pip install actuarialpy
```

## Quick start

Pass one tidy table — your experience at the grain you're analysing (one row per unit, e.g.
per group per month) — name its columns, and ask for views:

```python
import actuarialpy as ap

exp = ap.Experience(
    data,
    expense="claims",            # the loss / claim amount column(s)
    revenue="premium",           # the premium / revenue column(s)
    exposure="member_months",    # the exposure column(s)
    date="month",                # the time column
    profile="health",            # naming profile (health -> MLR, PMPM terminology)
)

exp.by("group_id")                          # grouped totals + loss ratio / MLR
exp.rolling(12, groupby="group_id")         # trailing-12 view per group
exp.trend(date_col="month",                 # period-over-period trend
          prior_start="2024-01-01", prior_end="2024-12-01",
          current_start="2025-01-01", current_end="2025-12-01")
```

You build `data` with pandas from whatever sources you have — typically a single `groupby`
that aggregates claims to your grain, counts member-months from eligibility, and joins
premium:

```python
g = ["group_id", "month"]
data = (claims.groupby(g)["paid_amount"].sum().rename("claims").to_frame()
        .join(eligibility.groupby(g).size().rename("member_months"))   # counted, not summed
        .join(premium.groupby(g)["premium"].sum().rename("premium"))
        .reset_index())
```

Counting member-months from eligibility — rather than summing a column that repeats across a
member's several claim rows — is the one thing to get right; everything else is ordinary
aggregation. Pick the grain to match the question: add `"service_type"` for a per-line view,
keep `member_id` for member-level work. For one-off numbers you can skip the object entirely
and call the [free functions](#ratios-and-per-exposure-metrics) on any aggregates.

## The `Experience` object

Binding the column roles once means every analysis reuses them — you never re-specify which
column is premium or how a loss ratio is computed. Bind `count` (a claim or service count) as
well to unlock the frequency-severity views (`frequency_severity`, `decompose_trend`).
`filter(...)` and `with_roles(...)` return new objects without mutating the original.

### `Experience` methods

| Method | Produces |
| --- | --- |
| `by(groupby)` | grouped totals and ratios |
| `views(views)` | a dict of named grouped summaries |
| `rolling(window, groupby)` | rolling-window summaries |
| `trend(prior/current windows, groupby)` | period-over-period trend |
| `components(...)` / `component_summary(...)` | component / driver breakdowns |
| `decompose_trend(...)` | utilization × unit cost (× mix) split |
| `actual_vs_expected(expected, actual, ...)` | actual-versus-expected with variances |
| `claimants(...)` / `top_claimants(...)` / `claimant_concentration(...)` | large-claimant and concentration views |
| `pool_claimants(claimant_col, pooling_point)` | pooled vs. excess by claimant |
| `cohort(...)` / `duration(...)` | cohort and duration summaries |
| `by_band(value_col, bands)` | banded summaries |
| `with_status(...)` / `by_status(...)` | lifecycle status assignment and summary |
| `margin(...)` | underwriting margins |
| `credibility_weighted(groupby, z, metric)` | credibility-blended estimates by group |
| `deseasonalize(factors)` / `complete(factors, valuation_date)` | new Experience with seasonality removed / claims developed to ultimate |
| `adjust(factors, on, by, how, audit_col)` | new Experience with a column restated by a joined factor |
| `filter(...)` / `with_roles(...)` | derive a new Experience |

## Ratios and per-exposure metrics

All of these accept scalars, NumPy arrays, or pandas Series, and divide safely (returning
NaN rather than raising on a zero denominator):

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

## Reserving

Build a development triangle from transactional claims, fit a chain ladder, and read off
ultimates and IBNR. Origin and development periods are derived for you.

```python
from actuarialpy import make_completion_triangle, ChainLadder, completion_factors

triangle = make_completion_triangle(
    claims, origin_col="incurred_month", valuation_col="paid_month",
    amount_col="paid", cumulative=True,
)

cl = ChainLadder.fit(triangle, method="volume", tail=1.0)
projection = cl.project(triangle)
# columns: latest_development, latest, development_factor, ultimate, ibnr

factors = completion_factors(triangle, method="volume", tail=1.0)   # 1 / cumulative DF
```

`ChainLadder.fit` exposes `age_to_age`, `cdf`, `completion_factors`, `tail`, and `method`.
Segment-level reserving needs no manual splitting — `chain_ladder_by` returns a
`{segment: ChainLadder}` mapping, and `completion_factors_by` returns a tidy table of
factors, one row per `(segment, development_month)`:

```python
from actuarialpy import completion_factors_by

cf_by_lob = completion_factors_by(
    claims, groupby="line_of_business",
    origin_col="incurred_month", valuation_col="paid_month", amount_col="paid",
    on_insufficient="skip",   # "raise", "skip", or "aggregate"
)
```

**Applying factors is kept separate from estimating them**, because applying hinges on a
join — each row's development period matched to the right factor. `apply_completion` matches
**by value** (the frame's index is irrelevant), takes each row's period as
`development_months(incurred, valuation)`, and treats rows past the triangle's last period
as fully complete, so only recent, immature months move:

```python
from actuarialpy import apply_completion

completed = apply_completion(
    latest_diagonal, factors,
    value_col="claims", date_col="incurred_month", valuation_date="2024-12-31",
)
# completed["claims_completed"] == paid / completion_factor

# per-segment factors: pass the tidy table + by=, joined on group AND development period
completed = apply_completion(
    latest_diagonal, cf_by_lob, by="line_of_business",
    value_col="claims", date_col="incurred_month", valuation_date="2024-12-31",
)
```

An absent `(group, period)` stays `NaN` (a surfaced gap, never silently filled), and a
duplicated key in the factor table is rejected rather than fanned out. **Other methods**
that blend emerged-to-date with an a priori are available through `develop_ultimate(...,
method=...)`: `"chain_ladder"`, `"bornhuetter_ferguson"` (with `apriori_col`), `"benktander"`,
and `"cape_cod"` (a priori derived from the data, taking `exposure_col`). All accept `by=`.
The library applies the method; it does not pick the a priori or the exposure base. On the
`Experience` facade, `complete(factors, valuation_date=...)` grosses the expense column up to
ultimate in place. Run completion **before** deseasonalizing and trending.

## Trend and forecasting

```python
from actuarialpy import trend_factor, annualized_trend, project_forward

trend_factor(0.06, months=18)             # (1 + 0.06) ** (18/12)
project_forward(1000.0, 0.06, months=18)  # trend a value forward 18 months
annualized_trend(current=1.1, prior=1.0, months_between=12)
```

The functions above *apply* a trend or measure it between two points. To *develop* a trend
from history, `fit_trend` regresses `log(rate)` on time (log-linear OLS) over the whole
series — using every period, so one noisy month doesn't swing it — and returns the fitted
annual trend, goodness of fit, and a confidence interval:

```python
from actuarialpy import fit_trend

fit = fit_trend(history, value_col="claims", date_col="month", exposure_col="member_months")
fit.annual_trend          # e.g. 0.072  (exp(slope) - 1)
fit.r_squared, fit.ci     # goodness of fit, confidence interval
fit.factor(18)            # (1 + annual_trend) ** (18/12)
```

It fits on the rate (`claims / member_months`) when an exposure is given, otherwise on the
value directly; time is measured from real dates, so a missing period is handled correctly.
Run it on completed, deseasonalized history (`complete → deseasonalize → fit_trend`) so
runout and seasonality don't bias the slope. Rate-based projection lives in the forecast
module: `forecast_experience(...)` applies a trended per-exposure rate to projected exposure.

## Utilization and PMPM decomposition

Split a per-member cost into utilization and unit cost, and decompose movement between two
periods — the standard "how much of the trend is util vs cost" exhibit. It needs a claim or
service count alongside losses and exposure, and is long-native (no reshaping):

```python
from actuarialpy import frequency_severity_summary, decompose_pmpm_trend

panel = frequency_severity_summary(
    df, count_col="claim_count", loss_col="claims", exposure_col="member_months",
    groupby="plan",
)
# columns: plan, member_months, claim_count, claims, frequency, severity, util_per_1000, pmpm
# pmpm == frequency * severity for every row

trend = decompose_pmpm_trend(
    prior_year, current_year,
    count_col="claim_count", loss_col="claims", exposure_col="member_months",
    on="plan",            # optional; omit for a single total row
)
# pmpm_trend == util_trend * cost_trend (exact); pmpm_change == util_effect + cost_effect
```

Pass `mix_by` to split PMPM three ways — utilization × unit cost × **mix** — when your book
is a blend of cells whose composition is shifting (otherwise a book-wide util or cost trend
silently absorbs membership-mix shifts). The split uses LMDI (logarithmic mean Divisia
index), which is order-free and leaves no residual; every cell must have positive count,
loss, and exposure in both periods. On an `Experience`, the same split is
`exp.decompose_trend(...)`, using the bound `count`, `expense`, and `exposure` roles. See
[`examples/trend_decomposition.py`](examples/trend_decomposition.py).

## Seasonality and working days

Two months of claims are rarely comparable as-is — a month may have fewer working days, and
the time of year matters on its own. Two separate tools handle the two effects.

`seasonality_factors` learns one multiplier per calendar period from a few years of history
(the classical ratio-to-moving-average decomposition, normalized to average 1.0). Pass
`exposure_col` to fit on a rate (PMPM), which removes membership growth so only the
time-of-year pattern remains:

```python
from actuarialpy import seasonality_factors, deseasonalize, apply_seasonality

factors = seasonality_factors(history, date_col="month", value_col="claims",
                              exposure_col="member_months")
deseasonalize(recent, factors, date_col="month", value_col="claims")   # pattern divided out
apply_seasonality(annual_plan, factors, date_col="month", value_col="budget")  # multiplied back
```

`business_days_in_period` counts weekdays minus holidays (US federal by default, no extra
dependency) for the residual year-to-year wrinkle; when using both, normalize by working
days first, then fit factors on the normalized series. On the `Experience` object,
`deseasonalize(factors)` divides the pattern out of the expense column in place and returns
a new `Experience`, so every downstream view composes on the deseasonalized series.
`seasonality_factors_by` fits per segment and returns a tidy `(segment, season)` table; pass
it with `by=` to `deseasonalize`. A rolling-12 or full-year comparison already cancels
seasonality, so reach for this mainly when fitting trend on month-level data.

## Adjustments and restatement

Much of experience rating is one move repeated: take a base amount and carry it through a
chain of factors — completion, trend, benefit relativity, area, demographic loads, network
discounts. `adjust` is that move: join a factor to each row by a key and multiply (or
divide). `complete` and `deseasonalize` are specializations that derive the key from a date;
`adjust` keys on an ordinary column. All share the same validated join (unique-key /
fan-out guard, surfaced gaps, index-independent).

```python
from actuarialpy import adjust

adjust(experience, 1.072, value_col="claims")                    # a scalar trend factor
area = pd.Series({"urban": 1.08, "suburban": 1.00, "rural": 0.94})
adjust(experience, area, value_col="claims", on="region")        # a Series keyed by a column
adjust(experience, benefit_relativity, value_col="claims",       # a tidy per-segment table
       on="plan", by="line_of_business")
```

`how="multiply"` (default) loads up; `how="divide"` backs a factor out. An absent key
surfaces as `NaN`; pass `default=1.0` when missing should mean "no adjustment". On the
`Experience` facade, `adjust` restates the expense column in place, and `audit_col` carries
the cumulative restatement multiplier across the chain for a reviewable trail:

```python
restated = (
    exp.complete(cf_by_lob, valuation_date="2024-12-31", by="line_of_business")
       .adjust(1.072, audit_col="restatement")                                     # trend
       .adjust(benefit_relativity, on="plan", by="line_of_business", audit_col="restatement")
       .adjust(area, on="region", audit_col="restatement")
)
restated.by()   # grouped loss ratios on the fully restated claims
```

## Actual versus forecast

Compare actuals against a forecast by supplying the two as separate tables — a database
pull for paids, a finance workbook for the forecast — and aligning them:

```python
from actuarialpy.forecast import compare_actual_to_expected

variance = compare_actual_to_expected(
    actuals_table, forecast_table,
    on=["month", "segment", "product", "category"],
    actual_col="amount", expected_col="amount",
    how="outer",                         # keep forecast months without actuals yet
    suffixes=("actual", "forecast"),     # -> amount_actual, amount_forecast
)
# columns: <keys...>, amount_actual, amount_forecast, variance, variance_pct, actual_to_expected
```

With `how="outer"`, a future month that has a forecast but no actual yet is kept with the
missing side `NaN`, so unavailable actuals stay distinguishable from a true zero. When
`category` mixes units (dollars and counts), keep it in the keys or filter to one category
before totalling.

## Credibility

Greatest-accuracy credibility, fit empirically from per-risk observations or constructed
from known structural parameters:

```python
from actuarialpy import Buhlmann, BuhlmannStraub, credibility_weighted_estimate

observations = [[10, 12, 9, 11], [20, 18, 22, 19], [5, 6, 4, 7]]   # rows are risks
model = Buhlmann.fit(observations)
model.z, model.k                      # credibility factor and constant
model.premium(risk_mean=11.0)         # credibility-weighted premium

ws = BuhlmannStraub.fit(observations, weights=[[1,1,1,1],[2,2,2,2],[1,1,1,1]])  # unequal exposures
credibility_weighted_estimate(observed=0.82, complement=0.75, z=0.6)            # blend directly
```

For the limited-fluctuation (classical) credibility most group experience rating uses — the
square-root rule against a full-credibility standard — use `limited_fluctuation_z`:

```python
from actuarialpy import limited_fluctuation_z, full_credibility_claims, credibility_weighted_estimate

groups["z"] = limited_fluctuation_z(groups["claim_count"], full_credibility_standard=1082)
groups["blended_lr"] = credibility_weighted_estimate(groups["experience_lr"], manual_lr, groups["z"])

n_full = full_credibility_claims(confidence=0.90, tolerance=0.05)   # ~1082 claims, from first principles
```

`Buhlmann(overall_mean, epv, vhm, n_obs)` and `BuhlmannStraub(...)` can also be constructed
directly when EPV and VHM are already known.

## Lifecycle, pooling, banding, margins

- **Lifecycle** (`lifecycle`): `is_in_force(...)`, `earned_exposure(...)`,
  `add_months_in_force(...)`, `add_tenure(...)`, and `derive_status(...)` (labels rows
  active / first-year / termed).
- **Pooling** (`pooling`): `pool_losses(df, loss_col, pooling_point)` splits each loss into
  pooled and excess; `excess_over_threshold(...)` isolates the excess layer. Long-native.
- **Banding** (`banding`): `assign_band(df, value_col, bands)` and `summarize_by_band(...)`.
- **Margins** (`margins`): `add_margin(...)` / `margin(...)` / `margin_ratio(...)`.
- **Contribution** (`contribution`): `share_of_total(...)`, `contribution_to_change(...)`,
  `top_contributors(...)`.

## Reporting

Write a set of named analysis views to a multi-sheet Excel workbook:

```python
from actuarialpy.reporting import to_excel_report

views = exp.views({"overall": None, "by_group": "group_id"})
to_excel_report(views, "experience_report.xlsx")
```

## The ActuarialPy ecosystem

ActuarialPy is the deterministic, experience-and-data layer of a small family of actuarial
packages. It is standalone (only `numpy` and `pandas`). Three companion packages cover the
distributional and simulation side and interoperate through a simple `.sample()` / `.mean()`
interface:

- **`lossmodels`** — frequency and severity distributions, aggregate (collective-risk) loss
  models, coverage modifications, and model fitting.
- **`risksim`** — portfolio loss simulation and aggregate reinsurance program evaluation.
- **`extremeloss`** — extreme value theory: tail fitting (POT/GPD, block maxima/GEV), tail
  risk measures, and threshold diagnostics.

## Testing

```bash
pytest -q
```

## License

MIT License
