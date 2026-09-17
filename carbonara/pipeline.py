"""One deterministic pass: materialize → normalize → fill → footprint, with provenance.

The view and the demo share this entry so a re-run reproduces records, footprint,
ledger, and lineage byte-for-byte. Run context (``run_id``, ``created_at``) is
injected, never read from the clock (§8.2).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

import pandas as pd

from carbonara.anomalies import detect_anomalies
from carbonara.apply_review import AppliedApproval, apply_approvals
from carbonara.augment import augment_lineage
from carbonara.fill import fill_weights
from carbonara.footprint import FootprintResult, compute_footprint
from carbonara.ledger import Ledger, run_id_for
from carbonara.lineage import apply_lineage, to_frame
from carbonara.materialize import SourceRecord, materialize
from carbonara.normalize import normalize_records
from carbonara.references import reference_digest
from carbonara.rules import AnomalyCategory, Finding, RuleEvent, Severity

__all__ = ["PipelineResult", "run"]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class PipelineResult:
    """The output of one run: final records, footprint, and both provenance stores."""

    records: list[SourceRecord]
    footprint: FootprintResult
    events: list[RuleEvent]
    findings: list[Finding]
    ledger: Ledger
    frame: pd.DataFrame
    run_id: str
    ruleset_version: str
    factor_version: str
    reference_digest: str
    resolved_cells: frozenset[tuple[str, str]] = frozenset()


def run(
    rows: Sequence[Mapping[str, str]],
    mapping: Mapping[str, str],
    *,
    content_hash: str,
    created_at: str,
    factor_version: str = "v1",
    ruleset_version: str = "v1",
    approvals: Sequence[AppliedApproval] = (),
) -> PipelineResult:
    """Run the full connector over accepted rows and return records + provenance.

    ``content_hash`` and the rule/factor versions derive the ``run_id`` (no clock,
    no uuid); ``created_at`` is the injected ledger timestamp. The frame carries
    the canonical columns plus ``estimated_kgco2e``, each touched cell tagged with
    its Bloodline source.

    ``approvals`` re-applies reviewer-approved rules as a deterministic second pass
    right after normalize, so a corrected material flows into fill and footprint; a
    re-applied cell's approval lineage chains onto its normalize source rather than
    clobbering it (§8.1). Empty ``approvals`` reproduces the single-pass output
    exactly.

    ``findings`` carries the reviewable events: uncertain mappings and implausible
    values from normalize/fill/footprint, plus the anomaly net (validity,
    completeness, duplicate-key, cross-field, distribution) run on the pre-fill
    records. Everything is surfaced for review, nothing silently corrected (§7.3).
    """
    normalized = normalize_records(materialize(rows, mapping))
    applied = apply_approvals(normalized.records, approvals)
    filled = fill_weights(applied.records)
    footprint = compute_footprint(filled.records, filled.events, factor_version=factor_version)

    # The approval events are recorded in the ledger like any rule, but their
    # lineage is attached via augment (chained), so they are kept out of the
    # clobbering apply_lineage pass below.
    lineage_events = normalized.events + applied.seed_events + filled.events + footprint.events
    events = normalized.events + applied.seed_events + applied.approval_events + filled.events + footprint.events
    # Anomalies are detected on the pre-fill records: "missing weight" must fire on
    # the cell as it arrived, before the ladder fills it (a filled weight is an
    # estimate, not the observed value). Additive and reviewable — never a silent
    # edit (§7.3); the categories are disjoint from the mapping/plausibility
    # findings above, so finding ids cannot collide.
    anomalies = detect_anomalies(applied.records)
    findings = normalized.findings + anomalies + filled.findings + footprint.findings
    if not rows:
        # A header-only file passes the drift gate (schema matches, no data) and
        # would otherwise yield a silent "0 kgCO₂e" — surface the emptiness so an
        # empty catalog is not indistinguishable from a healthy one.
        findings = [
            Finding.create(
                record_id="source",
                column=None,
                category=AnomalyCategory.VALIDITY,
                severity=Severity.HIGH,
                message="source has no data rows",
            )
        ]
    # Key the run to the reference data's bytes, not just the version label: an edit
    # to any factor or vocabulary is then a new, detectable run (§8.3).
    ref_digest = reference_digest(footprint.factor_version)
    run_id = run_id_for(content_hash, f"{ruleset_version}:{footprint.factor_version}:{ref_digest}")

    ledger = Ledger()
    ledger.extend(events, run_id=run_id, created_at=created_at)

    estimates = {c.record_id: c.estimated_kgco2e for c in footprint.components if c.estimated_kgco2e is not None}
    frame = to_frame(filled.records)
    frame = frame.assign(estimated_kgco2e=frame["record_id"].map(estimates))
    frame = apply_lineage(frame, lineage_events)
    for chain in applied.chains:
        mask = frame["record_id"].isin(chain.record_ids)
        frame = augment_lineage(frame, record=chain.record, row_mask=mask, column=chain.column)

    return PipelineResult(
        records=filled.records,
        footprint=footprint,
        events=events,
        findings=findings,
        ledger=ledger,
        frame=frame,
        run_id=run_id,
        ruleset_version=ruleset_version,
        factor_version=footprint.factor_version,
        reference_digest=ref_digest,
        resolved_cells=frozenset((e.record_id, e.column) for e in applied.approval_events),
    )
