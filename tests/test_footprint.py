"""The footprint costs weight × factor, flags the unmapped, and proves each estimate."""

from __future__ import annotations

from carbonara.contract import CanonicalRecord, QualityStatus
from carbonara.footprint import FootprintStatus, by_material, compute_footprint, summarize
from carbonara.materialize import SourceRecord
from carbonara.rules import AnomalyCategory, RuleEvent, SourceType


def _record(
    rid: str,
    *,
    material_raw: str = "cotton",
    material_normalized: str | None = None,
    component_weight_g: float | None = None,
    quality_status: QualityStatus = QualityStatus.OK,
) -> SourceRecord:
    record = CanonicalRecord(
        record_id=rid,
        source_row_id=rid.lstrip("r"),
        style_id="TSH-1",
        sku="S",
        component="shell fabric",
        material_raw=material_raw,
        material_normalized=material_normalized,
        component_weight_g=component_weight_g,
        supplier_raw="Acme",
        quality_status=quality_status,
    )
    return SourceRecord(record=record, raw={})


def test_costed_component_derives_weight_kg_times_factor():
    [rec] = compute_footprint(
        [_record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=200.0)], []
    ).components
    assert rec.status is FootprintStatus.COSTED
    assert rec.estimated_kgco2e is not None
    assert round(rec.estimated_kgco2e, 3) == 1.66  # 0.2 kg × 8.3
    assert rec.mapping_confidence == 1.0


def test_costed_component_emits_a_derived_formula_event_with_factor_version():
    result = compute_footprint(
        [_record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=200.0)], []
    )
    [event] = result.events
    assert event.source_type is SourceType.DERIVED_FORMULA
    assert event.column == "estimated_kgco2e"
    assert event.method_params["factor_version"] == "ecobalyse-2024.1"
    assert event.method_params["weight_source"] == "observed"


def test_unresolved_material_is_unmapped_and_flagged_not_costed_at_zero():
    result = compute_footprint(
        [_record("r0001", material_raw="Organic cottn", material_normalized=None, component_weight_g=200.0)], []
    )
    [rec] = result.components
    assert rec.status is FootprintStatus.UNMAPPED
    assert rec.estimated_kgco2e is None
    assert result.events == []  # nothing derived, nothing to cost
    assert any(f.category is AnomalyCategory.MAPPING for f in result.findings)


def test_missing_weight_is_no_weight():
    [rec] = compute_footprint(
        [_record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=None)], []
    ).components
    assert rec.status is FootprintStatus.NO_WEIGHT
    assert rec.estimated_kgco2e is None


def test_flagged_weight_is_derived_but_excluded_from_the_total():
    records = [
        _record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=200.0),
        _record(
            "r0002",
            material_raw="cotton",
            material_normalized="cotton",
            component_weight_g=5000.0,
            quality_status=QualityStatus.FLAGGED,
        ),
    ]
    result = compute_footprint(records, [])
    summary = summarize(result)
    assert summary.costed_n == 1 and summary.flagged_n == 1
    assert round(summary.total_kgco2e, 3) == 1.66  # the 5000 g flagged row is not summed


def test_filled_weight_propagates_its_range_and_is_labeled_filled():
    fill = RuleEvent.create(
        record_id="r0001",
        column="component_weight_g",
        rule_id="weight_median",
        rule_version="v1",
        source_type=SourceType.GROUPED_MEDIAN,
        value_before="",
        value_after="200.0",
        uncertainty_range=(180.0, 220.0),
    )
    [rec] = compute_footprint(
        [_record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=200.0)], [fill]
    ).components
    assert rec.weight_source == "filled"
    assert rec.uncertainty_kgco2e == (180.0 / 1000 * 8.3, 220.0 / 1000 * 8.3)


def test_summary_shares_split_observed_and_filled_by_kgco2e():
    fill = RuleEvent.create(
        record_id="r0002",
        column="component_weight_g",
        rule_id="weight_constant",
        rule_version="v1",
        source_type=SourceType.REFERENCE_CONSTANT,
        value_before="",
        value_after="100.0",
        uncertainty_range=(90.0, 300.0),
    )
    records = [
        _record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=100.0),
        _record("r0002", material_raw="cotton", material_normalized="cotton", component_weight_g=100.0),
    ]
    summary = summarize(compute_footprint(records, [fill]))
    assert round(summary.observed_share, 3) == 0.5 and round(summary.filled_share, 3) == 0.5


def test_by_material_sorts_largest_first():
    records = [
        _record("r0001", material_raw="cotton", material_normalized="cotton", component_weight_g=1000.0),
        _record("r0002", material_raw="polyester", material_normalized="polyester", component_weight_g=100.0),
    ]
    breakdown = by_material(compute_footprint(records, []))
    assert [b.key for b in breakdown] == ["cotton", "polyester"]
