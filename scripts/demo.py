"""The five-minute walkthrough: upload → drift gate → review → approve → re-run → trace.

A scripted, deterministic story over the fixture BOM. Lives outside ``carbonara/``
because it does file I/O and prints; every value it shows comes from the connector's
own deterministic functions, and the injected ``created_at`` / approval decision keep
the run reproducible. Run ``python scripts/demo.py``.
"""

from __future__ import annotations

import csv
import pathlib
import tempfile

from carbonara.apply_review import applications_from
from carbonara.augment import lineage_history
from carbonara.footprint import summarize
from carbonara.ingest import admit
from carbonara.pipeline import PipelineResult, run
from carbonara.review import ReviewQueue

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_DECISIONS = _ROOT / "fixtures" / "review_decisions.jsonl"
_MAPPING = {"vendor": "supplier"}
_CREATED_AT = "2026-01-01T00:00:00Z"  # injected, not wall-clock — keeps the story reproducible
#: The cell the walkthrough follows end to end (a planted `Organic cottn` typo).
_FOCUS = "r0065"


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _pipeline(digest: str, approvals: list | None = None) -> PipelineResult:
    return run(_rows(), _MAPPING, content_hash=digest, created_at=_CREATED_AT, approvals=approvals or [])


def walkthrough() -> list[str]:
    """Build the narrated walkthrough as an ordered list of lines (deterministic)."""
    lines: list[str] = ["carbonara — five-minute walkthrough", ""]

    # 1–2. Upload the file; the schema-drift gate holds it for review because the
    # `vendor` header drifts from the expected `supplier`, and proposes the rename
    # (never applied silently). The confirmed mapping is what the pipeline runs.
    with tempfile.TemporaryDirectory() as store:
        admitted = admit(_BOM_V1, pathlib.Path(store))
    digest = admitted.content_hash
    proposal = admitted.mapping_proposal
    renames = ", ".join(f"{src} → {dst}" for src, dst in proposal.renames.items()) if proposal else "none"
    lines.append(f"1. upload      · {_BOM_V1.name} · content hash {digest[:16]}")
    lines.append(f"2. drift gate  · {admitted.status.value}; proposes rename {renames} (confirmed before ingest)")

    # 3. Review queue: the Organic cottn mapping is proposed, never auto-applied.
    before = _pipeline(digest)
    finding = next(f for f in before.findings if f.record_id == _FOCUS and f.category.value == "mapping")
    lines.append(f"3. review      · {len(before.findings)} findings; {_FOCUS} {finding.message}")
    lines.append(f"               proposes {finding.proposed_value!r} — surfaced, not applied")

    # 4. Approve: replay the recorded decision (actor and timestamp injected).
    queue = ReviewQueue(before.findings)
    queue.replay(_DECISIONS.read_text(encoding="utf-8"))
    approvals = applications_from(queue)
    decision = queue.get(finding.finding_id).decisions[-1]
    lines.append(f"4. approve     · {decision.actor} approved at {decision.at} → 1 reusable alias rule")

    # 5. Re-run with the approval applied as a deterministic second pass.
    after = _pipeline(digest, approvals)
    resolved = sorted({rid for rid, _ in after.resolved_cells})
    lines.append(f"5. re-run      · approvals applied to {len(resolved)} cells: {', '.join(resolved)}")

    # 6–7. Fill + footprint: the corrected material now costs.
    cell = after.frame.loc[after.frame["record_id"] == _FOCUS].iloc[0]
    before_sum, after_sum = summarize(before.footprint), summarize(after.footprint)
    lines.append(
        f"6. fill        · {_FOCUS} material {cell['material_normalized']!r}, weight {cell['component_weight_g']:.0f} g"
    )
    lines.append(
        f"7. footprint   · costed {before_sum.costed_n} → {after_sum.costed_n} lines; "
        f"catalog {before_sum.total_kgco2e:.1f} → {after_sum.total_kgco2e:.1f} kgCO₂e"
    )

    # 8. Provenance trace: the ledger's two events and the chained spine lineage.
    material_events = [r for r in after.ledger.for_record(_FOCUS) if r.column == "material_normalized"]
    ledger_trail = " → ".join(f"{r.rule_id} ({r.value_before}→{r.value_after})" for r in material_events)
    tiers = _lineage_tiers(after, _FOCUS)
    lines.append(f"8. provenance  · ledger: {ledger_trail}")
    lines.append(f"               spine: {' › '.join(tiers)}")
    return lines


def _lineage_tiers(result: PipelineResult, record_id: str) -> list[str]:
    cell = result.frame.loc[result.frame["record_id"] == record_id].iloc[0]["data_lineage"]["material_normalized"]
    return [str(entry["source_type"]) for entry in lineage_history(cell)]


def main() -> None:
    print("\n".join(walkthrough()))


if __name__ == "__main__":
    main()
