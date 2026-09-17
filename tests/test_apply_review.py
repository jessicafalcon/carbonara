"""Re-apply pass: approved rules correct their cells, chained not clobbered."""

from __future__ import annotations

from carbonara.apply_review import AppliedApproval, apply_approvals
from carbonara.contract import CanonicalRecord
from carbonara.materialize import SourceRecord
from carbonara.review import ApprovedRule, ReviewDecision, ReviewStatus
from carbonara.rules import SourceType


def _record(record_id: str, *, material_raw: str, material_normalized: str | None = None) -> SourceRecord:
    return SourceRecord(
        record=CanonicalRecord(
            record_id=record_id,
            source_row_id=record_id.lstrip("r").lstrip("0") or "0",
            style_id="TSH-11",
            category="TSH",
            sku=f"{record_id}-WHT-XS",
            component="shell fabric",
            material_raw=material_raw,
            material_normalized=material_normalized,
            supplier_raw="Acme Textiles",
        ),
        raw={},
    )


def _alias_approval(*, actor: str = "reviewer", at: str = "2026-01-01T00:00:00Z") -> AppliedApproval:
    return AppliedApproval(
        rule=ApprovedRule(
            rule_id="alias:Organic cottn",
            rule_version="v1",
            source_type=SourceType.REFERENCE_RESOLVE,
            record_id="r0065",
            column="material_normalized",
            value="organic cotton",
            key="Organic cottn",
        ),
        decision=ReviewDecision(status=ReviewStatus.APPROVED, actor=actor, at=at),
    )


def test_alias_corrects_every_matching_unresolved_cell():
    records = [
        _record("r0065", material_raw="Organic cottn"),
        _record("r0100", material_raw="cotton", material_normalized="cotton"),
        _record("r0145", material_raw="Organic cottn"),
    ]
    result = apply_approvals(records, [_alias_approval()])
    corrected = {r.record.record_id: r.record.material_normalized for r in result.records}
    assert corrected == {"r0065": "organic cotton", "r0100": "cotton", "r0145": "organic cotton"}
    # One reusable approval -> two matched cells, each with a seed + approval event.
    assert [e.record_id for e in result.seed_events] == ["r0065", "r0145"]
    assert [e.record_id for e in result.approval_events] == ["r0065", "r0145"]
    assert result.chains[0].record_ids == ("r0065", "r0145")


def test_already_resolved_cell_is_never_clobbered():
    records = [_record("r0065", material_raw="Organic cottn", material_normalized="cotton")]
    result = apply_approvals(records, [_alias_approval()])
    assert result.records[0].record.material_normalized == "cotton"  # untouched
    assert result.seed_events == [] and result.approval_events == [] and result.chains == []


def test_seed_chains_normalize_then_reference_resolve():
    result = apply_approvals([_record("r0065", material_raw="Organic cottn")], [_alias_approval()])
    [seed] = result.seed_events
    [approval] = result.approval_events
    assert (seed.source_type, seed.value_before, seed.value_after) == (
        SourceType.NORMALIZE_MATERIAL,
        "Organic cottn",
        "organic cottn",
    )
    # The approval reads the seed's output and resolves it, carrying the decision.
    assert (approval.source_type, approval.value_before, approval.value_after) == (
        SourceType.REFERENCE_RESOLVE,
        "organic cottn",
        "organic cotton",
    )
    assert approval.method_params["actor"] == "reviewer"
    assert result.chains[0].record.source_type == "reference_resolve"


def test_per_cell_correction_matches_by_record_id_without_a_seed():
    records = [_record("r0088", material_raw="linen"), _record("r0089", material_raw="linen")]
    approval = AppliedApproval(
        rule=ApprovedRule(
            rule_id="approve:r0088:factory_country_iso:validity",
            rule_version="v1",
            source_type=SourceType.REFERENCE_RESOLVE,
            record_id="r0088",
            column="factory_country_iso",
            value="PT",
            key=None,
        ),
        decision=ReviewDecision(status=ReviewStatus.APPROVED, actor="a", at="2026-01-01T00:00:00Z"),
    )
    result = apply_approvals(records, [approval])
    corrected = {r.record.record_id: r.record.factory_country_iso for r in result.records}
    assert corrected == {"r0088": "PT", "r0089": None}  # only the one record
    assert result.seed_events == []  # per-cell correction synthesizes no normalize base
    assert [e.record_id for e in result.approval_events] == ["r0088"]


def test_empty_approvals_is_a_no_op():
    records = [_record("r0065", material_raw="Organic cottn")]
    result = apply_approvals(records, [])
    assert result.records == records
    assert (result.seed_events, result.approval_events, result.chains) == ([], [], [])


def test_re_apply_is_byte_identical_across_runs():
    records = [_record("r0145", material_raw="Organic cottn"), _record("r0065", material_raw="Organic cottn")]
    first = apply_approvals(records, [_alias_approval()])
    second = apply_approvals(records, [_alias_approval()])
    assert [e.event_id for e in first.approval_events] == [e.event_id for e in second.approval_events]
    assert first.chains == second.chains
    assert [r.record for r in first.records] == [r.record for r in second.records]
