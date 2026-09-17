"""Fill-accuracy metric: the fixed rule's error against held-out ground truth (§12).

This measures a *fixed* rule — QA, reported, never gated on a tuned threshold.
Selecting among methods by score is the overbuild this deliberately avoids.
"""

from __future__ import annotations

import dataclasses
import statistics
from collections import defaultdict

from carbonara.rules import RuleEvent, SourceType

__all__ = ["AccuracyReport", "TierAccuracy", "fill_accuracy"]

_FILL_TIERS = frozenset({SourceType.GROUPED_MEDIAN, SourceType.REFERENCE_CONSTANT, SourceType.DERIVED_FORMULA})


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class TierAccuracy:
    """Error of one tier's fills against ground truth."""

    n: int
    mae: float
    mape: float


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class AccuracyReport:
    """Overall and per-tier fill accuracy."""

    overall: TierAccuracy
    by_tier: dict[str, TierAccuracy]


def _score(errors: list[tuple[float, float]]) -> TierAccuracy:
    """Aggregate (absolute error, true value) pairs into MAE and MAPE."""
    if not errors:
        return TierAccuracy(n=0, mae=0.0, mape=0.0)
    mae = statistics.fmean(abs_err for abs_err, _ in errors)
    mape = statistics.fmean(abs_err / true for abs_err, true in errors if true) * 100
    return TierAccuracy(n=len(errors), mae=round(mae, 4), mape=round(mape, 4))


def fill_accuracy(events: list[RuleEvent], truth: dict[str, float]) -> AccuracyReport:
    """Measure filled weights against held-out truth, overall and per tier.

    ``truth`` maps ``record_id`` to the true value. Only fills with a known truth
    are scored. MAE is the mean absolute error; MAPE the mean absolute percentage
    error.
    """
    per_tier: dict[str, list[tuple[float, float]]] = defaultdict(list)
    overall: list[tuple[float, float]] = []
    for event in events:
        # Scope to weight fills: the footprint also emits DERIVED_FORMULA events,
        # on the estimated_kgco2e column, which are not weight fills to score.
        if event.column != "component_weight_g" or event.source_type not in _FILL_TIERS or event.value_after is None:
            continue
        true = truth.get(event.record_id)
        if true is None:
            continue
        abs_err = abs(float(event.value_after) - true)
        per_tier[event.source_type.value].append((abs_err, true))
        overall.append((abs_err, true))
    return AccuracyReport(
        overall=_score(overall),
        by_tier={tier: _score(errors) for tier, errors in sorted(per_tier.items())},
    )
