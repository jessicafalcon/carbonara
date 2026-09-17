"""One deterministic pass: materialize → normalize → fill → footprint, with provenance.

The view and the demo share this entry so a re-run reproduces records, footprint,
ledger, and lineage byte-for-byte. Run context (``run_id``, ``created_at``) is
injected, never read from the clock (§8.2).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

import pandas as pd

from carbonara.fill import fill_weights
from carbonara.footprint import FootprintResult, compute_footprint
from carbonara.ledger import Ledger, run_id_for
from carbonara.lineage import apply_lineage, to_frame
from carbonara.materialize import SourceRecord, materialize
from carbonara.normalize import normalize_records
from carbonara.rules import Finding, RuleEvent

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


def run(
    rows: Sequence[Mapping[str, str]],
    mapping: Mapping[str, str],
    *,
    content_hash: str,
    created_at: str,
    factor_version: str = "v1",
    ruleset_version: str = "v1",
) -> PipelineResult:
    """Run the full connector over accepted rows and return records + provenance.

    ``content_hash`` and the rule/factor versions derive the ``run_id`` (no clock,
    no uuid); ``created_at`` is the injected ledger timestamp. The frame carries
    the canonical columns plus ``estimated_kgco2e``, each touched cell tagged with
    its Bloodline source.
    """
    normalized = normalize_records(materialize(rows, mapping))
    filled = fill_weights(normalized.records)
    footprint = compute_footprint(filled.records, filled.events, factor_version=factor_version)

    events = normalized.events + filled.events + footprint.events
    findings = normalized.findings + filled.findings + footprint.findings
    run_id = run_id_for(content_hash, f"{ruleset_version}:{footprint.factor_version}")

    ledger = Ledger()
    ledger.extend(events, run_id=run_id, created_at=created_at)

    estimates = {c.record_id: c.estimated_kgco2e for c in footprint.components if c.estimated_kgco2e is not None}
    frame = to_frame(filled.records)
    frame = frame.assign(estimated_kgco2e=frame["record_id"].map(estimates))
    frame = apply_lineage(frame, events)

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
    )
