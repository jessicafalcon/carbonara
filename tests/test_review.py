"""Review queue: approve/reject with history, and approvals minting rules."""

from __future__ import annotations

import pathlib

from carbonara.review import ReviewQueue, ReviewStatus
from carbonara.rules import AnomalyCategory, Finding, Severity


def _mapping_finding(record_id: str = "r0065") -> Finding:
    return Finding.create(
        record_id=record_id,
        column="material_normalized",
        category=AnomalyCategory.MAPPING,
        severity=Severity.MEDIUM,
        message="'Organic cottn' near 'organic cotton'",
        proposed_value="organic cotton",
        evidence={"raw_value": "Organic cottn"},
    )


def test_decision_history_is_appended_never_rewritten():
    queue = ReviewQueue([_mapping_finding()])
    fid = _mapping_finding().finding_id
    queue.reject(fid, actor="a")
    item = queue.approve(fid, actor="b", note="on second look")
    assert [d.status for d in item.decisions] == [ReviewStatus.REJECTED, ReviewStatus.APPROVED]
    assert item.status is ReviewStatus.APPROVED


def test_pending_excludes_decided_items():
    queue = ReviewQueue([_mapping_finding()])
    assert len(queue.pending()) == 1
    queue.approve(_mapping_finding().finding_id, actor="a")
    assert queue.pending() == ()


def test_approved_mapping_becomes_a_versioned_rule():
    queue = ReviewQueue([_mapping_finding()])
    assert queue.approved_rules() == []  # nothing until approved
    queue.approve(_mapping_finding().finding_id, actor="a")
    [rule] = queue.approved_rules()
    assert (rule.key, rule.value, rule.rule_version) == ("Organic cottn", "organic cotton", "v1")


def test_rejected_mapping_mints_no_rule():
    queue = ReviewQueue([_mapping_finding()])
    queue.reject(_mapping_finding().finding_id, actor="a")
    assert queue.approved_rules() == []


def test_mapping_rule_is_a_reusable_alias():
    queue = ReviewQueue([_mapping_finding()])
    queue.approve(_mapping_finding().finding_id, actor="a")
    [rule] = queue.approved_rules()
    assert rule.key == "Organic cottn"  # reusable — matches every cell spelled this way
    assert (rule.record_id, rule.column) == ("r0065", "material_normalized")
    assert rule.rule_id == "alias:Organic cottn"


def _validity_finding_with_value() -> Finding:
    return Finding.create(
        record_id="r0088",
        column="factory_country_iso",
        category=AnomalyCategory.VALIDITY,
        severity=Severity.LOW,
        message="'Portugl' near 'Portugal'",
        proposed_value="PT",
    )


def _completeness_flag() -> Finding:
    return Finding.create(
        record_id="r0090",
        column="component_weight_g",
        category=AnomalyCategory.COMPLETENESS,
        severity=Severity.HIGH,
        message="weight missing",
    )


def test_non_mapping_approval_with_value_mints_a_per_cell_rule():
    queue = ReviewQueue([_validity_finding_with_value()])
    queue.approve(_validity_finding_with_value().finding_id, actor="a")
    [rule] = queue.approved_rules()
    assert rule.key is None  # per-cell, not a reusable alias
    assert (rule.record_id, rule.column, rule.value) == ("r0088", "factory_country_iso", "PT")
    assert rule.rule_id == "approve:r0088:factory_country_iso:validity"


def test_approved_flag_without_proposed_value_mints_nothing():
    queue = ReviewQueue([_completeness_flag()])
    queue.approve(_completeness_flag().finding_id, actor="a")
    assert queue.approved_rules() == []  # no value to re-apply — never guessed (§15)


def test_decisions_round_trip_through_jsonl():
    findings = [_mapping_finding(), _validity_finding_with_value()]
    original = ReviewQueue(findings)
    original.reject(_mapping_finding().finding_id, actor="a")
    original.approve(_mapping_finding().finding_id, actor="b", at="2026-01-01T00:00:00Z")
    original.approve(_validity_finding_with_value().finding_id, actor="a", at="2026-01-01T00:00:00Z")

    replayed = ReviewQueue(findings)
    replayed.replay(original.decisions_jsonl())

    # Same file replayed onto the same findings reproduces the history and the rules.
    assert replayed.decisions_jsonl() == original.decisions_jsonl()
    assert replayed.approved_rules() == original.approved_rules()
    assert [d.actor for d in replayed.get(_mapping_finding().finding_id).decisions] == ["a", "b"]


def test_replay_ignores_blank_lines():
    queue = ReviewQueue([_mapping_finding()])
    queue.replay(
        '\n{"actor": "r", "at": null, "finding_id": "r0065:material_normalized:mapping", '
        '"note": null, "status": "approved"}\n\n'
    )
    assert queue.get(_mapping_finding().finding_id).status is ReviewStatus.APPROVED


def test_fixture_decisions_are_canonical_and_approve_the_alias():
    path = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "review_decisions.jsonl"
    jsonl = path.read_text(encoding="utf-8").strip()
    queue = ReviewQueue([_mapping_finding()])
    queue.replay(jsonl)
    assert queue.decisions_jsonl() == jsonl  # the fixture is already in canonical form
    [rule] = queue.approved_rules()
    assert (rule.key, rule.value) == ("Organic cottn", "organic cotton")
