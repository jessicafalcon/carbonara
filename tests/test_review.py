"""Review queue: approve/reject with history, and approvals minting rules."""

from __future__ import annotations

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
