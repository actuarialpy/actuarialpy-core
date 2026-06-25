# actuarialpy examples

Self-contained, runnable examples for the main surfaces of `actuarialpy`. Each
script generates its own small synthetic data (via `_sample_data.py`) and prints
a short report, so they run with nothing but the package installed:

```bash
pip install actuarialpy
python experience_basics.py
```

Every script is standalone — run any one directly, in any order.

| Script | Surface | What it shows |
|---|---|---|
| `experience_basics.py` | `Experience` facade, metrics | Bind roles once; `.by`, `.views`; metric primitives (`loss_ratio`, `pmpm`, `pure_premium`) |
| `claimant_concentration.py` | claimants, pooling | `claimant_concentration`, `top_claimants`, `large_claimant_flags`, `pool_losses`, `excess_over_threshold` |
| `reserving_ibnr.py` | reserving | `make_completion_triangle` → `completion_factors` → `apply_completion` → `ibnr`, plus per-line `completion_factors_by` + grouped `apply_completion(by=)` |
| `seasonality.py` | seasonality | `business_days_in_period`, `seasonality_factors` → `deseasonalize`, plus per-line `seasonality_factors_by` + grouped `deseasonalize(by=)` |
| `trend_and_forecast.py` | trend | `trend_summary`, `annualized_trend`, `project_forward`, `trend_factor` |
| `credibility.py` | credibility | `credibility_weighted_estimate`, `Experience.credibility_weighted` |
| `lifecycle_and_banding.py` | lifecycle, banding | `derive_status`, `Experience.by_status`, `Experience.by_band` |

## The sample data

`_sample_data.py` (not part of the library) provides three deterministic generators:

- **`sample_member_months()`** — a member-month experience frame spanning
  2024–2025: claim components, rebates, non-FFS expense, premium, per-group
  effective/termination dates, and a subscriber count. A few members incur
  catastrophic claims so the concentration and pooling examples have a real tail.
- **`sample_claim_payments()`** — a long (line of business, origin, valuation,
  incremental-paid) frame for the reserving example, with a distinct payment
  pattern per line of business so the grouped completion join has something to
  separate; `make_completion_triangle` accumulates it into a cumulative triangle.
- **`sample_seasonal_panel()`** — a monthly claims panel by line of business and
  product over four years, with a real month-of-year seasonal pattern (one line
  swings hard, the other is mild), membership growth, and a cost trend, for the
  seasonality example.

## Note

These mirror the worked examples shipped alongside the sibling packages
(`lossmodels`, `risksim`, `extremeloss`). For an end-to-end application that wires
all four packages together, see the high-cost-claimant cost-model project.
