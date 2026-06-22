# Changelog

## 0.12.0

Adds per-segment completion factors -- fit a separate development pattern for each
line of business (or any split) from one dataset, instead of looping by hand.

### Added

- `chain_ladder_by(df, *, groupby, origin_col, valuation_col, amount_col, ...)` in
  `reserving`: groups the development data, builds a triangle per segment, and fits
  a `ChainLadder` to each, returning `{segment: ChainLadder}`.
- `completion_factors_by(...)`: the same, returned as a tidy
  `[<groupby>, lag_month, completion_factor]` table for review or joining.
- `InsufficientDataWarning`.

Segments too small to fit are handled by `on_insufficient`: `"raise"` (default,
names the failing segment), `"skip"` (omit them), or `"aggregate"` (use the pooled
whole-data pattern for them). A `warn` flag plus the standard `warnings` filters
control whether skipped/aggregated segments are reported -- use
`on_insufficient="skip", warn=False` to ignore thin segments silently. Both
functions are re-exported at the top level.

## 0.11.0

Adds chain-ladder estimation, so completion factors can now be **calculated** from
a development triangle rather than only supplied. This fills the gap between
building a triangle and applying factors.

### Added

- `ChainLadder` in the `reserving` module. `ChainLadder.fit(triangle, method=,
  tail=)` estimates a development pattern from a cumulative triangle (e.g. the
  output of `make_completion_triangle(..., cumulative=True)`) and exposes
  `age_to_age` (link factors), `cdf` (cumulative development factors to ultimate),
  and `completion_factors` (`1 / cdf`, divide-convention, in (0, 1]). `method` is
  volume-weighted (default) or simple-average; `tail` (>= 1) extends development
  past the latest observed lag. `ChainLadder.project(triangle)` returns per-origin
  latest, ultimate, and IBNR.
- `completion_factors(triangle, *, method=, tail=)` -- a one-line convenience
  returning just the completion-factor series.

Both are re-exported at the top level. The estimator is deterministic, so it lives
in `reserving` next to the triangle tooling rather than in a modeling satellite.

## 0.10.0

Sharpens the boundary around claims completion. Completing claims from a supplied
factor is a one-line multiply best done upstream, and a factor arriving in a
separate table needs a join only the caller can define unambiguously -- so factor
application is no longer part of the library. `Experience` is unchanged: bind
completed claims with the incurred date for the experience view, or paid claims
with the paid date for a finance / paid-basis view (every method already accepts a
`date_col` override, so one frame can even carry both dates).

### Removed (breaking)

- `complete_claims`, `complete_claim_components`, `completed_from_factor`, and
  `completed_experience`. Complete claims in your own pipeline (a single multiply,
  or a join you control), then pass the completed claims to `Experience`.
- The `completion` module is gone.

### Changed

- New `reserving` module holds the claims-development primitives that are *not* a
  one-line multiply: `make_completion_triangle`, `lag_months`, the `ibnr` identity,
  and `validate_completion_factors` (all still re-exported at the top level). These
  consume a compact development aggregate (origin x valuation), not line-level data.
- `make_completion_triangle` now returns a **cumulative** triangle by default (the
  usual basis for estimating development factors), with `cumulative=False` for the
  incremental triangle. The previous behavior was incremental but documented as
  cumulative; the flag makes the choice explicit.

## 0.9.0

Restores the capabilities removed during the Experience-centric refactor and
wires them into the new `Experience` object, plus fixes. The redesign itself
(the immutable `Experience` dataclass with `.filter()` / `.with_roles()`, the
`claimants` and `expected` modules) is kept.

### Added (restored)

- **Credibility** (`credibility`): `Buhlmann`, `BuhlmannStraub`, and
  `credibility_weighted_estimate`, plus a new `Experience.credibility_weighted`
  method that blends each group's metric with a complement at a given Z.
- **Lifecycle** (`lifecycle`): `derive_status`, `add_tenure`, `is_in_force`,
  `add_months_in_force`, `earned_exposure`, and the status constants, plus a new
  `Experience.with_status(...)` that returns a new `Experience` carrying a
  derived active/first-year/termed column (then summarize with `.by_status`).
- **Banding** (`banding`): `assign_band` and `summarize_by_band`, plus
  `Experience.by_band(...)`.
- **Margins** (`margins`): `margin`, `margin_ratio`, `add_margin`, plus
  `Experience.margin(...)` (computes margin from the bound roles, with an
  optional per-exposure margin).
- **Large-loss pooling** (`pooling`): `pool_losses` (cap at a pooling point →
  pooled/excess split) and `excess_over_threshold` (the per-claim excess sample
  that feeds tail/severity modeling in `extremeloss`/`lossmodels`/`risksim`),
  plus `Experience.pool_claimants(...)`. Descriptive large-claim flagging and
  concentration continue to live in `claimants` (`large_claimant_flags`,
  `claim_concentration`), so only the capping transform and the modeling
  hand-off were re-added.
- **`permissible_loss_ratio`** in `metrics` (CAS permissible / zero-margin loss
  ratio).
- **`completed_experience`** in `completion` (completion → experience in one
  call).

### Fixed

- **Default ratio name restored to `loss_ratio`.** `summarize_experience` had
  reverted to `expense_revenue_ratio` and `rolling_summary` to `mlr`; both now
  default to the general `loss_ratio` again (`profile="health"` still yields
  `mlr`).
- **Type-checking**: the package is mypy-clean again. Fixed pre-existing
  annotation issues in `metrics.safe_divide`, `trend` date-range narrowing,
  `forecast` merge `how`, and several `Experience` field/`filter`/`views`
  annotations.

## 0.8.0

Ergonomics: the `Experience` facade (bind the expense/revenue/exposure/profile
roles once, then `.by`/`.rolling`/`.trend`/`.by_band`/`.by_status`),
`completed_experience`, and a `trend_summary` fix so the period column no longer
leaks as `year_x`/`year_y`.

## 0.7.0

Generalized terminology across SOA and CAS lines (default ratio `loss_ratio`,
health available via the `health` profile) and added lifecycle, banding,
concentration, margins, and large-loss pooling, plus `permissible_loss_ratio`.
