"""RuleEvent / Finding id derivation and immutability."""

from __future__ import annotations

import dataclasses

import pytest

from carbonara.rules import AnomalyCategory, Finding, RuleEvent, Severity, SourceType


def test_event_id_is_deterministic_and_marks_original_null():
    event = RuleEvent.create(
        record_id="r0001",
        column="factory_country_iso",
        rule_id="country_iso",
        rule_version="v1",
        source_type=SourceType.NORMALIZE_COUNTRY,
        value_before="",
        value_after="PT",
    )
    assert event.event_id == "r0001:factory_country_iso:country_iso"
    assert event.is_original_null is True


def test_fill_event_carries_an_uncertainty_range():
    event = RuleEvent.create(
        record_id="r0040",
        column="component_weight_g",
        rule_id="weight_median",
        rule_version="v1",
        source_type=SourceType.GROUPED_MEDIAN,
        value_before="",
        value_after="154.0",
        uncertainty_range=(140.0, 168.0),
    )
    assert event.source_type is SourceType.GROUPED_MEDIAN
    assert event.uncertainty_range == (140.0, 168.0)
    assert event.is_original_null is True


def test_row_level_finding_has_no_column_in_id():
    finding = Finding.create(
        record_id="r0005",
        column=None,
        category=AnomalyCategory.DUPLICATE_KEY,
        severity=Severity.MEDIUM,
        message="duplicate (style, sku, component)",
    )
    assert finding.finding_id == "r0005:-:duplicate_key"


def test_records_are_frozen():
    event = RuleEvent.create(
        record_id="r0001",
        column="c",
        rule_id="r",
        rule_version="v1",
        source_type=SourceType.UNKNOWN,
        value_before="a",
        value_after="b",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.value_after = "x"  # ty: ignore[invalid-assignment]
