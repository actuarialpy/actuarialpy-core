"""Tests for the retention-stability primitives in actuarialpy.pooling."""
from __future__ import annotations

import numpy as np
import pytest

from actuarialpy import retained_cv, retention_for_target_cv


@pytest.fixture
def sample():
    rng = np.random.default_rng(0)
    return rng.lognormal(8.0, 1.3, 50_000)


def test_retained_cv_increases_with_retention(sample):
    # capping lower removes more tail variance, so the retained CV is smaller
    cvs = retained_cv(sample, np.array([10_000, 50_000, 200_000, 1_000_000]))
    assert np.all(np.diff(cvs) > 0)


def test_retained_cv_scales_with_sqrt_n(sample):
    one = retained_cv(sample, 100_000, n_units=1)
    hundred = retained_cv(sample, 100_000, n_units=100)
    assert hundred == pytest.approx(one / 10.0, rel=1e-12)


def test_scalar_returns_float_array_returns_ndarray(sample):
    assert isinstance(retained_cv(sample, 100_000), float)
    out = retained_cv(sample, np.array([50_000, 100_000]))
    assert isinstance(out, np.ndarray) and out.shape == (2,)


def test_retention_for_target_cv_round_trips(sample):
    # pick a target inside the achievable band, solve, and recompute the CV
    n = 500
    target = retained_cv(sample, 80_000.0, n_units=n)  # an achievable target by construction
    u = retention_for_target_cv(sample, n_units=n, target_cv=target)
    assert retained_cv(sample, u, n_units=n) == pytest.approx(target, rel=0.02)


def test_larger_groups_get_higher_retention(sample):
    # same target CV: more independent units -> higher retention
    target = 0.05
    u_small = retention_for_target_cv(sample, n_units=200, target_cv=target,
                                      bounds=(10_000, 2_000_000))
    u_large = retention_for_target_cv(sample, n_units=5_000, target_cv=target,
                                      bounds=(10_000, 2_000_000))
    assert u_large > u_small


def test_targets_clamp_to_bounds(sample):
    lo, hi = 10_000.0, 500_000.0
    # impossibly tight target -> floor; very loose target -> ceiling
    assert retention_for_target_cv(sample, 100, 1e-6, bounds=(lo, hi)) == pytest.approx(lo)
    assert retention_for_target_cv(sample, 100, 100.0, bounds=(lo, hi)) == pytest.approx(hi)


def test_empty_outcomes_raises():
    with pytest.raises(ValueError):
        retained_cv([], 100_000)
