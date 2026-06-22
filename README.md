# ActuarialPy

ActuarialPy is an experience-centered Python toolkit for actuarial analysis. It provides a lightweight `Experience` object for working with claims, losses, benefits, revenue, premium, exposure, and time-based experience data.

The core workflow is to define the actuarial roles of a dataset once, then use the object to produce common analyses such as experience summaries, rolling views, period-over-period trends, component drivers, actual-versus-expected summaries, claimant concentration reviews, and cohort/duration summaries.

## Installation

For local development:

```bash
pip install -e .
```

## Basic usage

```python
import actuarialpy as ap

exp = ap.Experience(
    claims,
    expense="total_expense",
    revenue="premium",
    exposure="member_months",
    date="incurred_date",
    profile="health",
)
```

Once the experience object is created, the same column roles are reused across analyses.

```python
summary = exp.by(["group_id", "product_code"])
rolling = exp.rolling(window=12, groupby="product_code")
trend = exp.trend(
    prior_start="2025-01-01",
    prior_end="2025-12-31",
    current_start="2026-01-01",
    current_end="2026-12-31",
    groupby="product_code",
)
```

## Core capabilities

ActuarialPy currently supports:

- grouped experience summaries
- loss ratio / MLR-style ratios (default `loss_ratio`; `mlr` via the health profile)
- PMPM, PSPM, PEPM, and generic per-exposure metrics
- development triangles and chain-ladder completion factors, overall or per segment (`reserving` module)
- rolling-window experience summaries
- period-over-period trend comparisons
- component-level driver analysis
- actual-versus-expected summaries
- claimant/member concentration review
- cohort and duration summaries
- lifecycle status (active / first-year / termed) and in-force exposure
- size banding and underwriting margins
- greatest-accuracy credibility (Bühlmann, Bühlmann-Straub) and credibility weighting
- large-loss pooling and the excess-over-threshold modeling hand-off
- permissible (target / zero-margin) loss ratio
- validation utilities for common data issues

**Claims basis.** ActuarialPy does not complete claims for you. Completing claims
from a factor is a single multiply best done in your own pipeline, and a factor in
a separate table needs a join only you can define. Bind whatever claims you have:
completed claims with the incurred date for an experience view, or paid claims with
the paid date for a finance / paid-basis view. The `reserving` module holds the
development work that is *not* a one-line multiply (triangles, lag, the IBNR
identity) and consumes a compact origin x valuation aggregate, not line-level data.

## Package structure

```text
actuarialpy/
├── frame.py        # Experience facade
├── metrics.py      # Ratios, per-exposure metrics, frequency, severity, A/E, permissible LR
├── experience.py   # Grouped experience summaries
├── reserving.py    # Triangles, chain-ladder completion factors, lag, IBNR identity
├── rolling.py      # Rolling-window summaries
├── trend.py        # Period and date-range trend summaries
├── components.py   # Component summaries and driver analysis
├── expected.py     # Actual-versus-expected summaries
├── claimants.py    # Claimant and concentration summaries
├── cohorts.py      # Cohort and duration summaries
├── lifecycle.py    # Status (active/first-year/termed) and in-force exposure
├── banding.py      # Size banding
├── margins.py      # Underwriting margins
├── credibility.py  # Bühlmann / Bühlmann-Straub credibility
├── pooling.py      # Large-loss pooling and excess-over-threshold hand-off
├── periods.py      # Period and duration helpers
└── columns.py      # Validation and column helpers
```

## Experience summaries

```python
summary = exp.by(["group_id", "product_code"])
```

Typical output includes:

```text
group_id
product_code
total_expense
total_revenue
member_months
mlr
expense_pmpm
revenue_pmpm
```

You can also create multiple views from the same experience object:

```python
views = exp.views({
    "overall": None,
    "by_group": "group_id",
    "by_product": "product_code",
    "by_group_product": ["group_id", "product_code"],
})
```

## Rolling summaries

```python
rolling = exp.rolling(
    window=12,
    groupby="product_code",
)
```

Rolling summaries include `period_start` and `period_end`. Incomplete windows are omitted by default.

## Trend summaries

Trend comparisons can be based on date ranges:

```python
trend = exp.trend(
    prior_start="2025-01-01",
    prior_end="2025-12-31",
    current_start="2026-01-01",
    current_end="2026-12-31",
    groupby="product_code",
)
```

They can also be based on a period column:

```python
claims["year"] = claims["incurred_date"].dt.year

trend = exp.trend(
    period_col="year",
    prior_period=2025,
    current_period=2026,
    groupby="product_code",
)
```

## Component driver analysis

Component driver analysis explains which categories drove the change in total experience.

```python
drivers = exp.components(
    component_cols=[
        "inpatient_claims",
        "outpatient_claims",
        "professional_claims",
        "pharmacy_claims",
        "pharmacy_rebates",
        "non_ffs_expenses",
    ],
    prior_start="2025-01-01",
    prior_end="2025-12-31",
    current_start="2026-01-01",
    current_end="2026-12-31",
    groupby="product_code",
)
```

## Actual versus expected

```python
ae = exp.actual_vs_expected(
    expected="expected_expense",
    groupby="product_code",
)
```

This produces aggregated actual, expected, actual-to-expected, variance, and variance percentage fields.

## Claimant review

Claimant-level summaries are descriptive and do not apply pooling, capping, or stop-loss adjustments.

```python
claimants = exp.claimants(
    claimant_col="member_id",
    groupby="group_id",
)

top = exp.top_claimants(
    claimant_col="member_id",
    groupby="group_id",
    n=25,
)

concentration = exp.claimant_concentration(
    claimant_col="member_id",
    groupby="group_id",
)
```

## Cohort and duration summaries

```python
cohort = exp.cohort(
    entity_col="group_id",
    start_date_col="group_effective_date",
    duration_months=12,
    groupby="product_code",
)

duration = exp.duration(
    entity_col="group_id",
    start_date_col="group_effective_date",
    max_duration_month=24,
)
```

## Lifecycle status and in-force exposure

`with_status` derives an active / first-year / termed status from effective and
termination dates as of a reference date, and returns a new `Experience` you can
summarize by status.

```python
staged = exp.with_status(
    effective_col="group_effective_date",
    termination_col="group_termination_date",
    as_of="2026-12-31",
    first_year_months=12,
)

by_status = staged.by_status("status", entity_col="group_id")
```

The free functions `derive_status`, `add_tenure`, `is_in_force`,
`add_months_in_force`, and `earned_exposure` are also available directly.

## Size banding and margins

```python
by_band = exp.by_band(
    "subscriber_count",
    bands=[0, 5, 25, 100, float("inf")],
    labels=["1-4", "5-24", "25-99", "100+"],
)

margins = exp.margin("group_id", per_exposure_col="margin_pmpm")
```

`margin` aggregates the bound expense and revenue roles, then adds the margin
(`total_revenue - total_expense`), the margin ratio, and an optional
per-exposure margin.

## Credibility

`credibility_weighted` blends each group's metric toward a complement at a given
credibility Z. When the complement is omitted, the book-level value is used.

```python
blended = exp.credibility_weighted(
    "group_id",
    z=0.55,
    metric="loss_ratio",
)
```

The greatest-accuracy models `Buhlmann` and `BuhlmannStraub`, and the
`credibility_weighted_estimate` primitive, are available as free functions.

## Large-loss pooling

Pooling caps large losses before they enter a group's experience and emits the
excess for tail modeling. `pool_claimants` aggregates to claimant level and
splits each claimant into pooled and excess amounts.

```python
pooled = exp.pool_claimants("member_id", pooling_point=100_000)

# Excess-over-threshold sample to hand off to a tail/severity model
from actuarialpy import excess_over_threshold

claimants = exp.claimants(claimant_col="member_id")
excess = excess_over_threshold(claimants, "total_expense", threshold=100_000, keep_cols="member_id")
```

Descriptive large-claim flagging and concentration stay in the claimant review
helpers (`large_claimant_flags`, `claim_concentration`); pooling adds the capping
transform and the `excess`/`extremeloss`/`lossmodels` hand-off.

## Reserving: triangles and completion factors

Build a cumulative development triangle from a both-dates (incurred x valuation)
aggregate, then estimate completion factors with chain-ladder. The triangle's
input is a compact months x months aggregate -- produce it upstream with a
`GROUP BY incurred_month, paid_month` so the line-level volume stays in the
warehouse.

```python
from actuarialpy import make_completion_triangle, ChainLadder, completion_factors

triangle = make_completion_triangle(
    dev,                     # rows of (incurred date, valuation date, paid amount)
    origin_col="incurred_month",
    valuation_col="valuation_month",
    amount_col="paid",
    cumulative=True,
)

cl = ChainLadder.fit(triangle, method="volume", tail=1.0)
cl.completion_factors      # 1 / cdf by lag, in (0, 1]
cl.age_to_age              # link (age-to-age) factors
cl.project(triangle)       # per-origin latest, ultimate, IBNR

# or just the factors:
factors = completion_factors(triangle)
```

The resulting completion factors are divide-convention (`completed = paid /
factor`), so they apply to incomplete claims directly. Completion itself stays in
your pipeline -- the library estimates the factors and arranges the data, but does
not apply them to your experience extract.

### Per-segment factors

Fit a separate pattern for each line of business (or any split) from one frame:

```python
from actuarialpy import chain_ladder_by, completion_factors_by

patterns = chain_ladder_by(dev, groupby="line_of_business",
                           origin_col="incurred_month", valuation_col="valuation_month",
                           amount_col="paid")
patterns["A"].completion_factors            # factors for one segment

factors = completion_factors_by(dev, groupby=["line_of_business", "product_code"],
                                origin_col="incurred_month", valuation_col="valuation_month",
                                amount_col="paid")                 # tidy table, all segments
```

Segments too thin to fit are handled by `on_insufficient`: `"raise"` (default,
names the segment), `"skip"`, or `"aggregate"` (use the pooled whole-data
pattern). The `warn` flag and the standard `warnings` filters control reporting --
`on_insufficient="skip", warn=False` ignores thin segments silently. Segmenting
trades credibility for responsiveness, so very thin segments are often better
served by the aggregate pattern or by blending toward it.

## Functional API

The `Experience` object is the recommended workflow interface, but the underlying functions are also available directly:

```python
from actuarialpy.experience import summarize_experience
from actuarialpy.trend import trend_summary
from actuarialpy.components import component_driver_analysis
from actuarialpy.expected import summarize_actual_vs_expected
from actuarialpy.claimants import summarize_claimants, top_claimants, claim_concentration
```

## Development status

ActuarialPy is in early development. The current focus is on reliable experience-analysis workflows before expanding into more complex forecasting, seasonality, credibility, or reserving methods.
