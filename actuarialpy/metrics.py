"""Core actuarial metric primitives."""

from __future__ import annotations

from numbers import Number
from typing import Any, cast

import numpy as np
import pandas as pd


def safe_divide(numerator: Any, denominator: Any, *, fill_value: float = np.nan) -> Any:
    """Safely divide numerator by denominator, element-wise.

    Return-type contract:

    - scalar / scalar -> native ``float`` (or ``fill_value`` on a zero divisor)
    - if either input is a ``pandas.Series`` -> ``pandas.Series`` whose index and
      name follow the numerator (or the denominator when the numerator is scalar)
    - otherwise array-like -> ``numpy.ndarray``

    Zero denominators yield ``fill_value``. Inputs are combined positionally
    (NumPy broadcasting), so Series inputs are assumed to already be aligned.
    """
    if isinstance(numerator, Number) and isinstance(denominator, Number):
        if denominator == 0:
            return fill_value
        return cast(Any, numerator) / cast(Any, denominator)

    index = None
    name = None
    if isinstance(numerator, pd.Series):
        index, name = numerator.index, numerator.name
    elif isinstance(denominator, pd.Series):
        index, name = denominator.index, denominator.name

    numerator_arr = np.asarray(numerator, dtype=float)
    denominator_arr = np.asarray(denominator, dtype=float)
    numerator_b, denominator_b = np.broadcast_arrays(numerator_arr, denominator_arr)
    result = np.divide(
        numerator_b,
        denominator_b,
        out=np.full(numerator_b.shape, fill_value, dtype=float),
        where=denominator_b != 0,
    )
    if index is not None and result.ndim == 1 and len(result) == len(index):
        return pd.Series(result, index=index, name=name)
    return result


def ratio(numerator: Any, denominator: Any) -> Any:
    """Calculate a generic ratio as numerator divided by denominator."""
    return safe_divide(numerator, denominator)


def loss_ratio(losses_or_expenses: Any, revenue: Any) -> Any:
    """Calculate a loss ratio: losses or expenses divided by revenue."""
    return ratio(losses_or_expenses, revenue)


def medical_loss_ratio(claims: Any, premium: Any) -> Any:
    """Calculate a medical loss ratio: claims divided by premium."""
    return loss_ratio(claims, premium)


def expense_ratio(expenses: Any, revenue: Any) -> Any:
    """Calculate an expense ratio: expenses divided by revenue."""
    return ratio(expenses, revenue)


def combined_ratio(losses: Any, expenses: Any, revenue: Any) -> Any:
    """Calculate combined ratio: (losses + expenses) divided by revenue."""
    if isinstance(losses, pd.Series) or isinstance(expenses, pd.Series):
        combined = losses + expenses
    elif isinstance(losses, Number) and isinstance(expenses, Number):
        combined = cast(Any, losses) + cast(Any, expenses)
    else:
        combined = np.asarray(losses, dtype=float) + np.asarray(expenses, dtype=float)
    return ratio(combined, revenue)


def actual_to_expected(actual: Any, expected: Any) -> Any:
    """Calculate actual-to-expected: actual divided by expected."""
    return ratio(actual, expected)


def per_exposure(amount: Any, exposure: Any) -> Any:
    """Calculate amount per exposure unit."""
    return ratio(amount, exposure)


def pmpm(amount: Any, member_months: Any) -> Any:
    """Calculate amount per member month."""
    return per_exposure(amount, member_months)


def pspm(amount: Any, subscriber_months: Any) -> Any:
    """Calculate amount per subscriber month."""
    return per_exposure(amount, subscriber_months)


def pepm(amount: Any, employee_months: Any) -> Any:
    """Calculate amount per employee month."""
    return per_exposure(amount, employee_months)


def frequency(claim_count: Any, exposure: Any) -> Any:
    """Calculate claim frequency: claim count divided by exposure."""
    return ratio(claim_count, exposure)


def severity(losses: Any, claim_count: Any) -> Any:
    """Calculate severity: losses divided by claim count."""
    return ratio(losses, claim_count)


def pure_premium(losses: Any, exposure: Any) -> Any:
    """Calculate pure premium: losses divided by exposure."""
    return per_exposure(losses, exposure)


def required_revenue(expense: Any, target_ratio: Any) -> Any:
    """Revenue needed for an expense amount to hit a target ratio."""
    return safe_divide(expense, target_ratio)


def indicated_change(required: Any, current: Any) -> Any:
    """Indicated change from current to required amount."""
    return safe_divide(required, current) - 1
