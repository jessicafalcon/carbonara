"""Phase 5 exit gate: footprint, factor-revision diff, trace, and reproducibility (§12)."""

from __future__ import annotations

import csv
import pathlib

import pytest

from carbonara.footprint import FootprintStatus, by_material, factor_diff, summarize
from carbonara.ingest import content_hash
from carbonara.pipeline import PipelineResult, run
from carbonara.rules import SourceType
from carbonara.view import render_view

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _run(factor_version: str = "v1") -> PipelineResult:
    return run(
        _rows(),
        {"vendor": "supplier"},
        content_hash=content_hash(_BOM_V1.read_bytes()),
        created_at="2026-01-01T00:00:00Z",
        factor_version=factor_version,
    )


@pytest.fixture(scope="module")
def result() -> PipelineResult:
    return _run()


def test_footprint_is_computed_and_labeled(result):
    summary = summarize(result.footprint)
    assert summary.total_kgco2e > 0
    assert 0.0 < summary.observed_share < 1.0 and round(summary.observed_share + summary.filled_share, 6) == 1.0
    event = next(e for e in result.footprint.events if e.source_type is SourceType.DERIVED_FORMULA)
    assert event.method_params["factor_source_version"]  # every estimate cites its factor version
    filled = next(e for e in result.footprint.events if e.method_params["weight_source"] == "filled")
    assert filled.uncertainty_range is not None  # a filled weight propagates a range


def test_factor_revision_recomputes_with_a_diff_and_no_history_corruption(result):
    v2 = _run("v2")
    diff = factor_diff(result.records, result.events, from_version="v1", to_version="v2")
    assert result.run_id != v2.run_id  # a revision is a new run
    assert diff.delta_kgco2e != 0.0 and [r.material for r in diff.rows] == ["polyester"]
    # v1 ledger is untouched by the v2 run — the two are independent serializations.
    assert result.ledger.to_jsonl() == _run("v1").ledger.to_jsonl()


def test_a_displayed_number_traces_to_source_and_factor_version(result):
    cotton = next(b for b in by_material(result.footprint) if b.key == "cotton")
    rows = [
        c
        for c in result.footprint.components
        if c.material == "cotton" and c.status is FootprintStatus.COSTED and c.estimated_kgco2e is not None
    ]
    assert round(sum(c.estimated_kgco2e for c in rows), 6) == round(cotton.total_kgco2e, 6)

    rid = rows[0].record_id
    footprint_event = next(r for r in result.ledger.for_record(rid) if r.column == "estimated_kgco2e")
    assert footprint_event.method_params["factor_table_version"] == "v1"
    raw = next(s.raw for s in result.records if s.record.record_id == rid)
    assert raw["source_row_id"] == rid.lstrip("r").lstrip("0")


def test_a_rerun_reproduces_footprint_ledger_lineage_and_html():
    a, b = _run(), _run()
    assert [c for c in a.footprint.components] == [c for c in b.footprint.components]
    assert a.ledger.to_jsonl() == b.ledger.to_jsonl()
    assert a.frame["data_lineage"].astype(str).tolist() == b.frame["data_lineage"].astype(str).tolist()
    assert render_view(a) == render_view(b)
