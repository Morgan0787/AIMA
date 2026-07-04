from __future__ import annotations

from typing import Any

# Maps legacy 1-10 importance checks to normalized 0.0-1.0 scale.
HIGH_IMPORTANCE_THRESHOLD = 0.7

# Opportunity composite score: old formula used importance_1_10 * 0.5.
# On 0.0-1.0 scale the equivalent weight is * 5.0.
IMPORTANCE_OPPORTUNITY_WEIGHT = 5.0


def normalize_importance_score(value: Any, default: float = 0.3) -> float:
    """
    Normalize importance_score into [0.0, 1.0].

    Backward-compatible with legacy 1-10 values stored in older rows.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    if parsed <= 1.0:
        return max(0.0, min(1.0, parsed))
    if parsed <= 10.0:
        return max(0.0, min(1.0, parsed / 10.0))
    return 1.0


def importance_opportunity_contribution(value: Any, default: float = 0.3) -> float:
    """Return the opportunity-score contribution from a normalized importance value."""
    return normalize_importance_score(value, default=default) * IMPORTANCE_OPPORTUNITY_WEIGHT
