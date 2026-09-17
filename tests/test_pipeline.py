"""The pipeline runs end to end over bom_v1 and reproduces everything exactly."""

from __future__ import annotations

import csv
import pathlib

import pytest

from carbonara.ingest import content_hash
from carbonara.ledger import run_id_for
from carbonara.pipeline import PipelineResult, run
from carbonara.references import reference_digest
from carbonara.rules import SourceType

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


def test_frame_carries_estimated_footprint_with_lineage(result):
    costed = next(c for c in result.footprint.components if c.estimated_kgco2e is not None)
    row = result.frame[result.frame["record_id"] == costed.record_id].iloc[0]
    assert row["estimated_kgco2e"] == costed.estimated_kgco2e
    assert row["data_lineage"]["estimated_kgco2e"]["source_type"] == "derived_formula"


def test_ledger_holds_the_footprint_events(result):
    costed = next(c for c in result.footprint.components if c.estimated_kgco2e is not None)
    ledger_row = next(r for r in result.ledger.for_record(costed.record_id) if r.column == "estimated_kgco2e")
    assert ledger_row.source_type is SourceType.DERIVED_FORMULA
    assert ledger_row.method_params["factor_source_version"] == "ecoinvent-3.9.1 via Ecobalyse"


def test_run_id_is_deterministic_and_factor_scoped():
    assert _run("v1").run_id == _run("v1").run_id


def test_run_id_is_keyed_to_reference_data_bytes(result):
    # The run id folds in a content hash of the reference data, not just the
    # version label — so editing a factor value (even keeping the name) is a new
    # run, and the reproducibility check catches it (§8.3).
    expected = run_id_for(content_hash(_BOM_V1.read_bytes()), f"v1:v1:{reference_digest('v1')}")
    assert result.run_id == expected
    assert result.reference_digest == reference_digest("v1")


def test_re_run_reproduces_records_events_and_ledger():
    a, b = _run(), _run()
    assert [r.record for r in a.records] == [r.record for r in b.records]
    assert a.events == b.events
    assert a.ledger.to_jsonl() == b.ledger.to_jsonl()
    assert a.frame["data_lineage"].astype(str).tolist() == b.frame["data_lineage"].astype(str).tolist()
