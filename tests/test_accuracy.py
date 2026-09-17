"""Fill-accuracy aggregates the fixed rule's error by tier against ground truth."""

from __future__ import annotations

from carbonara.accuracy import fill_accuracy
from carbonara.rules import RuleEvent, SourceType


def _fill(record_id: str, tier: SourceType, value: str) -> RuleEvent:
    return RuleEvent.create(
        record_id=record_id,
        column="component_weight_g",
        rule_id="weight",
        rule_version="v1",
        source_type=tier,
        value_before="",
        value_after=value,
    )


def test_mae_and_mape_are_computed_per_tier():
    events = [
        _fill("r0001", SourceType.GROUPED_MEDIAN, "150.0"),  # true 154 → err 4
        _fill("r0002", SourceType.REFERENCE_CONSTANT, "300.0"),  # true 200 → err 100
    ]
    truth = {"r0001": 154.0, "r0002": 200.0}
    report = fill_accuracy(events, truth)
    assert report.by_tier["grouped_median"].mae == 4.0
    assert report.by_tier["reference_constant"].mae == 100.0
    assert report.overall.n == 2
    assert report.overall.mae == 52.0


def test_fills_without_known_truth_are_skipped():
    events = [_fill("r0001", SourceType.GROUPED_MEDIAN, "150.0")]
    assert fill_accuracy(events, truth={}).overall.n == 0


def test_normalization_events_are_ignored():
    events = [_fill("r0001", SourceType.NORMALIZE_UNIT, "150.0")]
    assert fill_accuracy(events, truth={"r0001": 154.0}).overall.n == 0
