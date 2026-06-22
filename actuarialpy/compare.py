"""Comparison and variance primitives."""

from __future__ import annotations

from typing import Any

from actuarialpy.metrics import safe_divide


def relative_change(numerator: Any, base: Any) -> Any:
    """Canonical relative change: ``numerator / base - 1``.

    All period-over-period, percent-change, and percent-variance helpers in the
    package delegate here so the definition lives in one place.
    """
    return safe_divide(numerator, base) - 1


def absolute_change(current: Any, prior: Any) -> Any:
    """Calculate current minus prior."""
    return current - prior


def percent_change(current: Any, prior: Any) -> Any:
    """Calculate percent change: current / prior - 1."""
    return relative_change(current, prior)


def basis_point_change(current_ratio: Any, prior_ratio: Any) -> Any:
    """Calculate basis point change between two decimal ratios."""
    return (current_ratio - prior_ratio) * 10_000


def variance(actual: Any, expected: Any) -> Any:
    """Calculate actual minus expected."""
    return actual - expected


def variance_pct(actual: Any, expected: Any) -> Any:
    """Calculate variance as percent of expected: actual / expected - 1."""
    return relative_change(actual, expected)
