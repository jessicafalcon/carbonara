"""The pipeline runs end to end over bom_v1 and reproduces everything exactly."""

from __future__ import annotations

import csv
import pathlib

import pandas as pd
import pytest

from carbonara.apply_review import AppliedApproval, applications_from
from carbonara.augment import lineage_history
from carbonara.ingest import content_hash
from carbonara.ledger import run_id_for
from carbonara.pipeline import PipelineResult, run
from carbonara.references import reference_digest
from carbonara.review import ReviewQueue
from carbonara.rules import SourceType

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_DECISIONS = _ROOT / "fixtures" / "review_decisions.jsonl"
#: The three planted `Organic cottn` cells the approved alias corrects (§6/§12).
_ALIASED = ("r0065", "r0145", "r0178")


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _run(factor_version: str = "v1", approvals: list[AppliedApproval] | None = None) -> PipelineResult:
    return run(
        _rows(),
        {"vendor": "supplier"},
        content_hash=content_hash(_BOM_V1.read_bytes()),
        created_at="2026-01-01T00:00:00Z",
        factor_version=factor_version,
        approvals=approvals or [],
    )


def _approvals() -> list[AppliedApproval]:
    """Replay the fixture decisions onto the run's findings and pair the approvals."""
    findings = _run().findings
    queue = ReviewQueue(findings)
    queue.replay(_DECISIONS.read_text(encoding="utf-8"))
    return applications_from(queue)


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


def test_empty_approvals_reproduces_the_single_pass_output():
    plain, empty = _run(), _run(approvals=[])
    assert plain.ledger.to_jsonl() == empty.ledger.to_jsonl()
    assert plain.frame["data_lineage"].astype(str).tolist() == empty.frame["data_lineage"].astype(str).tolist()
    assert plain.resolved_cells == frozenset()


def test_approval_resolves_and_costs_the_planted_cells():
    plain = _run()
    applied = _run(approvals=_approvals())
    # Unresolved and uncosted before approval; resolved and costed after.
    for record_id in _ALIASED:
        assert pd.isna(plain.frame.loc[plain.frame["record_id"] == record_id, "material_normalized"].iloc[0])
        row = applied.frame.loc[applied.frame["record_id"] == record_id].iloc[0]
        assert row["material_normalized"] == "organic cotton"
        assert row["estimated_kgco2e"] is not None
    assert applied.resolved_cells == {(rid, "material_normalized") for rid in _ALIASED}


def test_approved_cell_carries_a_two_entry_chained_lineage():
    applied = _run(approvals=_approvals())
    cell = applied.frame.loc[applied.frame["record_id"] == "r0065"].iloc[0]["data_lineage"]["material_normalized"]
    tiers = [entry["source_type"] for entry in lineage_history(cell)]
    assert tiers == ["normalize_material", "reference_resolve"]  # original + approval, chained
    assert cell["source_type"] == "reference_resolve"  # the head stays the latest rule


def test_re_apply_writes_both_events_to_the_ledger():
    applied = _run(approvals=_approvals())
    material_rows = [r for r in applied.ledger.for_record("r0065") if r.column == "material_normalized"]
    assert [r.rule_id for r in material_rows] == ["material_lower", "alias:Organic cottn"]
    approval = material_rows[1]
    assert approval.source_type is SourceType.REFERENCE_RESOLVE
    assert approval.method_params["actor"] == "reviewer" and approval.method_params["status"] == "approved"


def test_re_run_with_approvals_is_byte_identical():
    a = _run(approvals=_approvals())
    b = _run(approvals=_approvals())
    assert a.ledger.to_jsonl() == b.ledger.to_jsonl()
    assert a.frame["data_lineage"].astype(str).tolist() == b.frame["data_lineage"].astype(str).tolist()
