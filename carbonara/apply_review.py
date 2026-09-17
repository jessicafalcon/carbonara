"""Re-apply approved review rules to the cells they correct — the review loop's return.

An approved mapping (`Organic cottn` → `organic cotton`) is not merely minted as a
rule; this pass re-applies it to the cell it corrects (brief §10). The correction
chains onto the cell's original source rather than clobbering it: for a material
alias, the deterministic normalize step (lowercasing the raw material — the form
the reviewer saw) seeds the cell, and the approved resolution chains on top, so the
cell's lifecycle reads `normalize_material → reference_resolve` (§8.1, via
:func:`carbonara.augment.augment_lineage`). Both steps write ledger events (§8.2).

The pass is deterministic: the decision (actor, status, ``at``) is injected on each
:class:`AppliedApproval`, never read from the clock, and approvals are applied in a
sorted, stable order. Empty approvals is a no-op that returns the records unchanged.

>>> from carbonara.contract import CanonicalRecord
>>> from carbonara.materialize import SourceRecord
>>> from carbonara.review import ApprovedRule, ReviewDecision, ReviewStatus
>>> from carbonara.rules import SourceType
>>> record = SourceRecord(
...     record=CanonicalRecord(
...         record_id="r0065", source_row_id="65", style_id="TSH-11", category="TSH", sku="TSH-11-WHT-XS",
...         component="shell fabric", material_raw="Organic cottn", supplier_raw="Acme Textiles",
...     ),
...     raw={},
... )
>>> approval = AppliedApproval(
...     rule=ApprovedRule(
...         rule_id="alias:Organic cottn", rule_version="v1", source_type=SourceType.REFERENCE_RESOLVE,
...         record_id="r0065", column="material_normalized", value="organic cotton", key="Organic cottn",
...     ),
...     decision=ReviewDecision(status=ReviewStatus.APPROVED, actor="reviewer", at="2026-01-01T00:00:00Z"),
... )
>>> result = apply_approvals([record], [approval])
>>> result.records[0].record.material_normalized  # the cell is corrected
'organic cotton'
>>> [e.rule_id for e in result.seed_events], [e.rule_id for e in result.approval_events]
(['material_lower'], ['alias:Organic cottn'])
>>> chain = result.chains[0]
>>> chain.column, chain.record.source_type, chain.record_ids
('material_normalized', 'reference_resolve', ('r0065',))
>>> apply_approvals([record], []).records is not None  # empty approvals: no-op
True
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from carbonara.augment import RuleRecord
from carbonara.materialize import SourceRecord
from carbonara.review import ApprovedRule, ReviewDecision, ReviewQueue
from carbonara.rules import RuleEvent, SourceType

__all__ = ["AppliedApproval", "ApplyResult", "ApprovalChain", "apply_approvals", "applications_from"]

#: The base normalize step a material alias chains onto — the lowercasing the
#: reviewer saw before approving the resolution.
_MATERIAL_BASE_RULE = "material_lower"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class AppliedApproval:
    """An approved rule paired with the injected decision that authorized it."""

    rule: ApprovedRule
    decision: ReviewDecision


def applications_from(queue: ReviewQueue) -> list[AppliedApproval]:
    """The approvals to re-apply from a decided review queue, ready for :func:`apply_approvals`."""
    return [AppliedApproval(rule=rule, decision=decision) for rule, decision in queue.approved_rules_with_decisions()]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ApprovalChain:
    """One approval's lineage chain: a rule record to append to a column's cells."""

    column: str
    record: RuleRecord
    record_ids: tuple[str, ...]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ApplyResult:
    """The corrected records and the provenance the re-apply produced.

    ``seed_events`` are the base normalize events that seed each corrected cell's
    head source (they go to both the ledger and ``apply_lineage``); ``approval_events``
    are the approvals (ledger only — their lineage is attached via ``chains`` so it
    chains rather than clobbers).
    """

    records: list[SourceRecord]
    seed_events: list[RuleEvent]
    approval_events: list[RuleEvent]
    chains: list[ApprovalChain]


def _decision_params(decision: ReviewDecision) -> dict[str, object]:
    """The injected decision, flattened into a rule's method params (deterministic)."""
    return {"actor": decision.actor, "status": decision.status.value, "at": decision.at, "note": decision.note}


def apply_approvals(records: list[SourceRecord], approvals: Sequence[AppliedApproval]) -> ApplyResult:
    """Re-apply approved rules to the cells they correct, chaining each cell's lineage.

    A reusable material alias (``rule.key`` set) matches every record whose
    ``material_raw`` equals the key and whose target column is still unresolved; a
    per-cell correction (``rule.key`` ``None``) matches the one record it was raised
    on. Only unresolved cells are corrected — an approval never overwrites a value a
    rule already produced. Returns a new record list; the input is not mutated.
    """
    if not approvals:
        return ApplyResult(records=list(records), seed_events=[], approval_events=[], chains=[])

    out = list(records)
    seed_events: list[RuleEvent] = []
    approval_events: list[RuleEvent] = []
    chains: list[ApprovalChain] = []

    for approval in sorted(approvals, key=lambda a: a.rule.rule_id):
        rule = approval.rule
        matched_ids: list[str] = []
        for position, source in enumerate(out):
            record = source.record
            if getattr(record, rule.column) is not None:
                continue  # already resolved — never clobber (§8.3, no silent edit)
            if rule.key is not None:
                if record.material_raw != rule.key:
                    continue
            elif record.record_id != rule.record_id:
                continue

            before = record.material_raw if rule.key is not None else None
            if rule.key is not None:
                # A material alias chains onto the normalize step the reviewer saw:
                # emit the lowercasing base so the cell has a source to chain onto.
                lowered = record.material_raw.strip().lower()
                seed_events.append(
                    RuleEvent.create(
                        record_id=record.record_id,
                        column=rule.column,
                        rule_id=_MATERIAL_BASE_RULE,
                        rule_version="v1",
                        source_type=SourceType.NORMALIZE_MATERIAL,
                        value_before=record.material_raw,
                        value_after=lowered,
                    )
                )
                before = lowered

            approval_events.append(
                RuleEvent.create(
                    record_id=record.record_id,
                    column=rule.column,
                    rule_id=rule.rule_id,
                    rule_version=rule.rule_version,
                    source_type=rule.source_type,
                    value_before=before,
                    value_after=rule.value,
                    method_params=_decision_params(approval.decision),
                )
            )
            out[position] = dataclasses.replace(source, record=dataclasses.replace(record, **{rule.column: rule.value}))
            matched_ids.append(record.record_id)

        if matched_ids:
            chains.append(
                ApprovalChain(
                    column=rule.column,
                    record=RuleRecord(
                        rule_id=rule.rule_id,
                        rule_version=rule.rule_version,
                        source_type=rule.source_type.value,
                        inputs={"value": rule.value, **_decision_params(approval.decision)},
                    ),
                    record_ids=tuple(matched_ids),
                )
            )

    return ApplyResult(records=out, seed_events=seed_events, approval_events=approval_events, chains=chains)
