"""A factor revision recomputes metrics and diffs them without corrupting history (§12)."""

from __future__ import annotations

import csv
import pathlib

from carbonara.fill import fill_weights
from carbonara.footprint import factor_diff
from carbonara.ingest import content_hash
from carbonara.ledger import Ledger
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records
from carbonara.pipeline import run

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"


def _records():
    with _BOM_V1.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return fill_weights(normalize_records(materialize(rows, {"vendor": "supplier"})).records)


def test_only_the_revised_factor_moves_and_the_total_rises():
    filled = _records()
    diff = factor_diff(filled.records, filled.events, from_version="v1", to_version="v2")
    assert [r.material for r in diff.rows] == ["polyester"]  # only polyester's factor changed
    row = diff.rows[0]
    assert row.factor_from == 5.5 and row.factor_to == 6.1
    assert row.delta_kgco2e > 0
    assert round(diff.delta_kgco2e, 6) == round(row.delta_kgco2e, 6)  # catalog delta == the one moved material


def test_recompute_appends_under_a_new_run_id_leaving_v1_history_intact():
    rows_path = _BOM_V1
    with rows_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    kwargs = dict(content_hash=content_hash(rows_path.read_bytes()), created_at="2026-01-01T00:00:00Z")

    v1 = run(rows, {"vendor": "supplier"}, factor_version="v1", **kwargs)
    v2 = run(rows, {"vendor": "supplier"}, factor_version="v2", **kwargs)
    assert v1.run_id != v2.run_id  # a revision is a new run, not an overwrite

    # Append-only: both runs' events coexist and the v1 rows are byte-identical.
    ledger = Ledger()
    ledger.extend(v1.events, run_id=v1.run_id, created_at="t")
    v1_snapshot = ledger.to_jsonl()
    ledger.extend(v2.events, run_id=v2.run_id, created_at="t")
    after = ledger.to_jsonl()
    assert after.startswith(v1_snapshot)  # v1 history unchanged, v2 appended
    assert len(after) > len(v1_snapshot)
