# ActuarialPy

ActuarialPy is a Python toolkit for actuarial experience analysis. It provides reusable functions for common actuarial calculations, grouped experience summaries, completion (loss development) factor application, rolling experience views, trend comparisons, component-level driver analysis, lifecycle/in-force handling, size banding, concentration, margins, and large-loss pooling.

The package is general across lines of business — life, health, and pension under the SOA, and property/casualty under the CAS. Terminology defaults to the line-agnostic vocabulary (loss ratio, exposure, premium, losses); health is supported as a first-class application through the `health` profile (which produces familiar names such as `mlr` and per-member-per-month metrics). It is designed to sit on top of pandas rather than replace it, focusing on calculations where actuarial meaning matters, such as aggregating before calculating ratios, completing claims with development factors, normalizing by exposure, and comparing experience across periods.

## Installation

For local development:

```bash
pip install -e .
```

## Quick start

The `Experience` facade is the recommended entry point. Bind the expense, revenue, exposure, and (optionally) profile columns once, and each view becomes a single short call instead of repeating the column arguments.

```python
import actuarialpy as ap

exp = ap.Experience(
    claims,
    expense=["total_claims", "pharmacy_rebates", "non_ffs_expenses"],  # rebates are negative
    revenue="premium",
    exposure="member_months",
)

exp.by("line_of_business")                  # grouped experience; ratio column is loss_ratio
exp.by("product_code", profile="health")    # per-call override -> ratio named mlr, PMPM columns
exp.rolling(12, date_col="incurred_date", groupby="group_id", freq="MS")
exp.trend(amount_col="total_claims", period_col="year", prior_period=2025, current_period=2026)
exp.by_band("subscriber_count", bands=[0, 100, 250, float("inf")])
exp.by_status("status", entity_col="group_id")
exp.views({"book": None, "by_lob": "line_of_business"})
```

Each method delegates to the matching free function (`summarize_experience`, `rolling_summary`, `trend_summary`, `summarize_by_band`, `status_summary`, `cohort_summary`, `duration_summary`), which remain available directly for anything the facade does not cover. Any bound role can be overridden per call.

## Core capabilities

ActuarialPy supports:

- Basic actuarial metrics such as loss ratio, per-exposure metrics (PMPM/PSPM/PEPM as health conveniences), frequency, severity, pure premium, combined ratio, actual-to-expected, and the permissible (target/zero-margin) loss ratio.
- An optional `Experience` facade that binds the expense/revenue/exposure/profile roles once, so each view (`.by`, `.rolling`, `.trend`, `.by_band`, `.by_status`, `.cohort`, `.duration`) is a single short call.
- Grouped experience summaries by fields such as group, product, line of business, and incurred period (ratio column defaults to `loss_ratio`).
- Claim completion (loss development) calculations using paid completion factors, IBNR, and a `completed_experience` one-call completion-to-experience summary.
- Rolling-window summaries, including rolling 12-period loss ratio and per-exposure views.
- Trend summaries comparing two periods.
- Component-level driver analysis for arbitrary cost categories.
- Credibility weighting, including Bühlmann and Bühlmann-Straub models and a credibility-weighting primitive.
- Lifecycle handling: derive active / first-year / termed status and tenure from effective and termination dates, in-force flags, and exposure clipping / earned exposure.
- Size banding by any numeric measure, with per-band experience summaries.
- Concentration analysis (top-N cumulative and share) at group or member/claimant grain.
- Underwriting margin (premium net of losses and loadings) and per-exposure margin.
- Large-loss pooling: flagging, capping at a pooling point (pooled/excess split), large-loss summaries, and the excess-over-threshold hand-off to the modeling satellites.
- Validation utilities for common actuarial data issues.

## Package structure

```text
src/actuarialpy/
├── metrics.py       # Core ratios, exposure-normalized metrics, and actuarial primitives
├── completion.py    # Completion factors, completed claims, IBNR, and completed_experience
├── experience.py    # Grouped experience summaries and views
├── frame.py         # Experience facade: bind column roles once, delegate to the functions above
├── rolling.py       # Calendar-aware rolling-window experience summaries
├── trend.py         # Trend factors, projection, and period-over-period summaries
├── components.py    # Component summaries and driver analysis
├── contribution.py  # Share-of-total and contribution-to-change primitives
├── credibility.py   # Bühlmann / Bühlmann-Straub models and the weighting primitive
├── cohorts.py       # Cohort and duration summaries
├── lifecycle.py     # Status (active/first-year/termed), tenure, in-force, earned exposure
├── banding.py       # Configurable size bands and per-band summaries
├── concentration.py # Top-N cumulative and share (group or member/claimant grain)
├── margins.py       # Underwriting margin and per-exposure margin
├── pooling.py       # Large-loss flagging, pooling/capping, excess-over-threshold hand-off
├── forecast.py      # Rate-based forecasting and actual-to-expected comparison
├── periods.py       # Period and duration helpers
├── compare.py       # Variance and change calculations
├── columns.py       # Column validation and small DataFrame helpers
├── profiles.py      # Light-touch domain profile defaults (e.g. health -> mlr)
└── reporting.py     # Basic Excel report export
```

The `Experience` facade and most workflow functions are importable directly from the top level, e.g. `from actuarialpy import Experience, summarize_experience, rolling_summary`.

## Basic metrics

```python
from actuarialpy import loss_ratio, pmpm, permissible_loss_ratio

loss_ratio(850_000, 1_000_000)
# 0.85

pmpm(1_000_000, 2_000)
# 500.0

permissible_loss_ratio(0.136)        # 1 - expense_ratio - profit_provision
# 0.864
```

The metric primitives are vectorized and type-stable: scalar inputs return a native `float`, and `pandas.Series` inputs return a `Series` with the original index preserved (Series are combined positionally, so they are assumed aligned).

## Completion factors and IBNR

ActuarialPy assumes completion factors are supplied by the user. Joins between claims and factor tables should generally be handled directly with pandas.

```python
claims = claims.merge(
    factors,
    on=["line_of_business", "incurred_date"],
    how="left",
    validate="many_to_one",
)
```

Once the factors are joined, `complete_claim_components` adds completed and IBNR columns for each component (e.g. `inpatient_claims_completed`, `inpatient_claims_ibnr`).

```python
from actuarialpy.completion import complete_claim_components

claims = complete_claim_components(
    claims,
    component_factor_map={
        "inpatient_claims": "inpatient_completion_factor",
        "outpatient_claims": "outpatient_completion_factor",
        "professional_claims": "professional_completion_factor",
        "pharmacy_claims": "pharmacy_completion_factor",
    },
)
```

When the goal is experience on a completed basis, `completed_experience` does the completion and the summary in one call. The `*_completed` columns become the expense numerator, together with any `additional_expense_cols` that are summed as-is.

```python
from actuarialpy import completed_experience

summary = completed_experience(
    claims,
    component_factor_map={
        "inpatient_claims": "inpatient_completion_factor",
        "outpatient_claims": "outpatient_completion_factor",
        "professional_claims": "professional_completion_factor",
        "pharmacy_claims": "pharmacy_completion_factor",
    },
    revenue_cols="premium",
    groupby=["group_id"],
    exposure_cols="member_months",
    additional_expense_cols=["pharmacy_rebates", "non_ffs_expenses"],
)
```

## Experience summaries

This is what `Experience.by` wraps. For member-level monthly data, create a true exposure field before summarizing.

```python
claims["member_months"] = 1
```

Then summarize, passing the expense and revenue columns (they are aggregated before the ratio is taken, which avoids averaging row-level ratios).

```python
from actuarialpy import summarize_experience

summary = summarize_experience(
    claims,
    groupby=["group_id", "product_code"],
    expense_cols=["total_claims", "pharmacy_rebates", "non_ffs_expenses"],
    revenue_cols=["premium"],
    exposure_cols=["member_months"],
)
```

The output uses generic field names, with the ratio defaulting to `loss_ratio`:

```text
total_expense
total_revenue
loss_ratio
expense_pmpm
revenue_pmpm
```

Pass `profile="health"` to name the ratio `mlr` instead, or `ratio_name=`/`ratio_col=` for a custom name. ActuarialPy intentionally does not rename `total_expense` to `total_claims` or `total_revenue` to `total_premium`, since the numerator and denominator may include items beyond claims or premium.

## Rolling summaries

Rolling summaries are useful for reviewing longer-term experience patterns, such as a rolling 12-month loss ratio. The window is measured in calendar periods: each group is reindexed onto a dense, gap-free grid before rolling, so a missing month does not silently stretch the window across extra calendar time. Provide `freq` (a pandas offset alias such as `"MS"`) when the data has gaps or is not regularly spaced.

```python
from actuarialpy import rolling_summary

rolling = rolling_summary(
    claims,
    date_col="incurred_date",
    window=12,
    freq="MS",
    groupby=["group_id"],
    expense_cols=["total_claims", "pharmacy_rebates", "non_ffs_expenses"],
    revenue_cols=["premium"],
    exposure_cols=["member_months"],
)
```

Rolling summaries include `period_start`, `period_end`, the aggregated amounts, `loss_ratio`, and per-exposure metrics. Incomplete rolling windows are omitted by default.

## Trend summaries

Trend summaries compare experience between two periods, based on a period column such as calendar year.

```python
from actuarialpy import trend_summary

claims["year"] = claims["incurred_date"].dt.year

trend = trend_summary(
    claims,
    period_col="year",
    prior_period=2025,
    current_period=2026,
    groupby=["product_code"],
    amount_col="total_claims",
    exposure_col="member_months",
)
```

This compares per-exposure experience between the prior and current periods and reports the trend.

## Component driver analysis

Component driver analysis explains which categories drove a change in total per-exposure cost.

```python
from actuarialpy import component_driver_analysis

drivers = component_driver_analysis(
    claims,
    period_col="year",
    prior_period=2025,
    current_period=2026,
    groupby=["product_code"],
    component_cols=[
        "inpatient_claims",
        "outpatient_claims",
        "professional_claims",
        "pharmacy_claims",
    ],
    exposure_col="member_months",
)
```

The output shows prior per-exposure cost, current per-exposure cost, the change, the component trend, and each component's contribution to the total change.

## Lifecycle

Derive status and tenure from effective and termination dates rather than requiring a precomputed label, and clip exposure to the window each entity was in force. The module derives the distinction and provides the windowing levers; differential treatment of cohorts (for example, weighting first-year business in a renewal blend) is left to the caller.

```python
import actuarialpy as ap

groups = ap.derive_status(
    groups,
    effective_col="effective_date",
    termination_col="termination_date",
    as_of="2026-12-31",
    first_year_months=12,            # active / first_year / termed
)
groups = ap.add_tenure(groups, "effective_date", "2026-12-31")

# Whole months in force during a period (clipped to [effective, termination]).
groups = ap.add_months_in_force(
    groups,
    effective_col="effective_date",
    termination_col="termination_date",
    period_start="2026-01-01",
    period_end="2026-12-01",
)
```

Status can then drive a summary directly with `Experience.by_status("status", ...)` or `status_summary`.

## Size banding, concentration, and margins

```python
import actuarialpy as ap

# Experience by a size band on any numeric measure.
ap.summarize_by_band(
    claims, "subscriber_count", bands=[0, 100, 250, float("inf")],
    expense_cols=["total_claims"], revenue_cols=["premium"],
)

# How concentrated the book is, at group or member/claimant grain.
ap.concentration_summary(member_totals, by_col="member_id", amount_col="total_claims")

# Underwriting margin: premium net of losses and loadings, with optional per-exposure margin.
ap.add_margin(
    group_totals, premium_col="premium",
    expense_cols=["total_claims", "non_ffs_expenses"], ratio_col="margin_pct",
)
```

## Large-loss pooling

Experience rating pools (caps) large losses so a single catastrophic claim does not distort a group's experience. These helpers are the deterministic front end; the excess-over-threshold sample they produce is the hand-off to tail and aggregate modeling in the companion packages.

```python
import actuarialpy as ap

# Cap each loss at a pooling point: pooled (retained) + excess (pooled across the block).
pooled = ap.pool_losses(claimants, "loss", pooling_point=100_000)

ap.large_loss_summary(claimants, "loss", threshold=100_000, entity_col="member_id")

# Excess over threshold -> a GPD tail in extremeloss, severity/aggregate in lossmodels.
excess = ap.excess_over_threshold(claimants, "loss", threshold=100_000)
```

## Credibility

ActuarialPy provides the credibility-weighting primitive plus greatest-accuracy (Bühlmann and Bühlmann-Straub) credibility models, which sit next to the experience and ratemaking workflows that consume them.

```python
from actuarialpy import Buhlmann, credibility_weighted_estimate

# Fit a Bühlmann model from a (n_risks, n_obs) array of observations.
model = Buhlmann.fit(observations)
model.z                    # credibility factor Z = n / (n + K)
model.premium(risk_mean)   # Z * risk_mean + (1 - Z) * overall_mean

# The blend is also available directly, for a Z from any source
# (a model above, a filed credibility formula, or your own calculation).
credibility_weighted_estimate(observed=actual_pmpm, complement=manual_pmpm, z=0.6)
```

`BuhlmannStraub` is the exposure-weighted analogue, with `z(weight)` and `premium(risk_mean, weight)` taking per-risk exposure weights.

## Development status

ActuarialPy covers the core experience-analysis, ratemaking, and reserving workflows: metrics, completion/IBNR, grouped and rolling experience, trend, component drivers, credibility, lifecycle, banding, concentration, margins, and large-loss pooling. Planned additions include seasonality indices, enrollment-to-member-month exposure construction, and deterministic chain-ladder factor development. Stochastic loss modeling, simulation, and extreme-value/tail work live in the companion packages (`lossmodels`, `risksim`, and `extremeloss`).