"""§12 fill-ladder cases and dual-store provenance, end-to-end on bom_v1.csv."""

from __future__ import annotations

import csv
import pathlib

import pytest

from carbonara.accuracy import fill_accuracy
from carbonara.fill import FillResult, fill_weights
from carbonara.ledger import Ledger
from carbonara.lineage import apply_lineage, to_frame
from carbonara.materialize import materialize
from carbonara.normalize import NormalizeResult, normalize_records
from carbonara.rules import AnomalyCategory, SourceType

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"
_GROUND_TRUTH = _BOM_V1.parent / "ground_truth_v1.csv"


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _weight_truth() -> dict[str, float]:
    with _GROUND_TRUTH.open(newline="") as handle:
        return {
            f"r{int(row['source_row_id']):04d}": float(row["true_value"])
            for row in csv.DictReader(handle)
            if row["column"] == "component_weight_g"
        }


def _run() -> tuple[NormalizeResult, FillResult]:
    normalized = normalize_records(materialize(_rows(), {"vendor": "supplier"}))
    return normalized, fill_weights(normalized.records)


@pytest.fixture(scope="module")
def pipeline() -> tuple[NormalizeResult, FillResult]:
    return _run()


def _fill_event(filled: FillResult, source_row_id: int):
    rid = f"r{source_row_id:04d}"
    return next((e for e in filled.events if e.record_id == rid), None)


def _record(filled: FillResult, source_row_id: int):
    rid = f"r{source_row_id:04d}"
    return next(r for r in filled.records if r.record.record_id == rid)


def test_dense_tight_group_fills_by_grouped_median(pipeline):
    _, filled = pipeline
    for row_id in (40, 58, 71):
        assert _fill_event(filled, row_id).source_type is SourceType.GROUPED_MEDIAN


def test_high_spread_and_sparse_fall_through_to_reference_constant(pipeline):
    _, filled = pipeline
    assert _fill_event(filled, 314).source_type is SourceType.REFERENCE_CONSTANT
    assert _fill_event(filled, 317).source_type is SourceType.REFERENCE_CONSTANT


def test_implausible_observed_weight_is_flagged_not_changed(pipeline):
    _, filled = pipeline
    assert _record(filled, 46).record.component_weight_g == 5000.0
    assert _record(filled, 46).record.quality_status.value == "flagged"
    assert any(f.record_id == "r0046" and f.category is AnomalyCategory.PLAUSIBILITY for f in filled.findings)


def test_every_fill_is_labeled_in_both_stores(pipeline):
    normalized, filled = pipeline
    ledger = Ledger()
    ledger.extend(normalized.events + filled.events, run_id="run-test", created_at="2026-01-01T00:00:00Z")
    frame = apply_lineage(to_frame(filled.records), normalized.events + filled.events)

    ledger_row = next(r for r in ledger.for_record("r0040") if r.column == "component_weight_g")
    assert ledger_row.source_type is SourceType.GROUPED_MEDIAN
    n = ledger_row.method_params["n"]
    assert isinstance(n, int) and n >= 5
    assert ledger_row.uncertainty_range is not None

    lineage = frame[frame["record_id"] == "r0040"].iloc[0]["data_lineage"]
    assert lineage["component_weight_g"]["source_type"] == "grouped_median"


def test_fill_accuracy_is_reported_per_tier(pipeline):
    _, filled = pipeline
    report = fill_accuracy(filled.events, _weight_truth())
    assert report.overall.n == 97
    assert "grouped_median" in report.by_tier and "reference_constant" in report.by_tier
    assert report.overall.mae > 0  # measured, not claimed exact


def test_fill_ledger_and_lineage_reproduce_exactly():
    (norm_a, fill_a), (norm_b, fill_b) = _run(), _run()
    assert [r.record for r in fill_a.records] == [r.record for r in fill_b.records]
    assert fill_a.events == fill_b.events

    def serialize(norm, fill):
        ledger = Ledger()
        ledger.extend(norm.events + fill.events, run_id="run-test", created_at="t")
        frame = apply_lineage(to_frame(fill.records), norm.events + fill.events)
        return ledger.to_jsonl(), frame["data_lineage"].astype(str).tolist()

    assert serialize(norm_a, fill_a) == serialize(norm_b, fill_b)
