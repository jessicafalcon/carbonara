"""The ledger records rule events append-only, deterministically, with run context."""

from __future__ import annotations

from carbonara.ledger import Ledger, run_id_for
from carbonara.rules import RuleEvent, SourceType


def _fill_event(record_id: str) -> RuleEvent:
    return RuleEvent.create(
        record_id=record_id,
        column="component_weight_g",
        rule_id="weight_median",
        rule_version="v1",
        source_type=SourceType.GROUPED_MEDIAN,
        value_before="",
        value_after="154.0",
        method_params={"group": "material×component×category", "n": 5},
        uncertainty_range=(138.0, 170.0),
    )


def test_run_id_is_deterministic_from_inputs():
    assert run_id_for("abc123", "v1") == run_id_for("abc123", "v1")
    assert run_id_for("abc123", "v1") != run_id_for("abc123", "v2")


def test_ledger_promotes_events_with_run_context():
    ledger = Ledger()
    ledger.extend([_fill_event("r0040")], run_id="run1", created_at="2026-01-01T00:00:00Z")
    [row] = ledger.rows()
    assert row.run_id == "run1"
    assert row.source_type is SourceType.GROUPED_MEDIAN
    assert row.uncertainty_range == (138.0, 170.0)
    assert row.created_at == "2026-01-01T00:00:00Z"


def test_for_record_filters_the_history():
    ledger = Ledger()
    ledger.extend([_fill_event("r0040"), _fill_event("r0071")], run_id="r", created_at="t")
    assert len(ledger.for_record("r0040")) == 1


def test_serialization_is_deterministic_with_injected_context():
    a, b = Ledger(), Ledger()
    for ledger in (a, b):
        ledger.extend([_fill_event("r0040")], run_id="run1", created_at="t")
    assert a.to_jsonl() == b.to_jsonl()
