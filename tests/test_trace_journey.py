"""The exit-gate journey: a displayed number → footprint rows → rules → source + factor."""

from __future__ import annotations

import csv
import pathlib

from carbonara.footprint import FootprintStatus, by_material
from carbonara.ingest import content_hash
from carbonara.pipeline import run
from carbonara.rules import SourceType

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"

_WEIGHT_TIERS = {SourceType.GROUPED_MEDIAN, SourceType.REFERENCE_CONSTANT, SourceType.NORMALIZE_UNIT}


def _result():
    with _BOM_V1.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, run(
        rows, {"vendor": "supplier"}, content_hash=content_hash(_BOM_V1.read_bytes()), created_at="2026-01-01T00:00:00Z"
    )


def test_a_material_total_is_the_sum_of_its_component_rows():
    _, result = _result()
    cotton = next(b for b in by_material(result.footprint) if b.key == "cotton")
    rows = [
        c
        for c in result.footprint.components
        if c.material == "cotton" and c.status is FootprintStatus.COSTED and c.estimated_kgco2e is not None
    ]
    assert round(sum(c.estimated_kgco2e for c in rows), 6) == round(cotton.total_kgco2e, 6)


def test_a_displayed_number_traces_to_rules_source_row_and_factor_version():
    rows, result = _result()
    # Pick a costed cotton component whose weight was filled — the richest trace.
    component = next(
        c
        for c in result.footprint.components
        if c.material == "cotton" and c.weight_source == "filled" and c.status is FootprintStatus.COSTED
    )

    ledger_rows = result.ledger.for_record(component.record_id)
    footprint_event = next(r for r in ledger_rows if r.column == "estimated_kgco2e")
    weight_event = next(r for r in ledger_rows if r.column == "component_weight_g")

    assert footprint_event.source_type is SourceType.DERIVED_FORMULA
    assert footprint_event.method_params["factor_source_version"] == "ecobalyse-2024.1"
    assert footprint_event.method_params["factor_table_version"] == "v1"
    assert weight_event.source_type in _WEIGHT_TIERS  # the weight behind the estimate is itself traced

    # → the source file row the number ultimately rests on.
    raw = next(s.raw for s in result.records if s.record.record_id == component.record_id)
    assert raw["source_row_id"] == component.record_id.lstrip("r").lstrip("0")
