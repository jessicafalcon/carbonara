"""Preserve a cell's Bloodline lineage while attaching a new rule record (§8.1, §11).

Bloodline keeps one :class:`~bloodline.Source` per cell, and ``override=True``
replaces it — so the spine holds the *current* value's source, not the ordered
lifecycle of the rules that produced it (§8.1, "known limit"). This helper closes
that gap without leaving Bloodline: the cell's head ``Source`` stays the latest
rule (every read, merge, and ER diagram still works), and the ordered lifecycle
rides in the head's ``source_metadata`` under a reserved ``"lineage"`` key — an
oldest-first list of rule records. ``source_metadata`` is free-form by design, so
this uses Bloodline as intended rather than reimplementing lineage.

It is the append-only counterpart to :func:`carbonara.lineage.apply_lineage`,
which clobbers. The per-cell list is a projection onto one cell — light metadata
only, no clock and no ids — and does not duplicate the ledger's cross-cell,
append-only history (§8.2); it carries no timestamp, so this module stays in the
deterministic data path.

Depends only on Bloodline, pandas, and the standard library, so the helper is
liftable upstream unchanged; the connector's ladder tiers appear only in the
example and tests.

>>> import bloodline as bl
>>> from carbonara.augment import RuleRecord, augment_source, lineage_history
>>> # A material cell first normalized, then resolved against the reference list.
>>> normalized = bl.Source(
...     source_type="normalize_material",
...     source_metadata={"rule_id": "material_lower", "rule_version": "v1"},
... )
>>> resolved = RuleRecord(
...     rule_id="material_resolve", rule_version="v1",
...     source_type="reference_resolve", confidence=0.9,
... )
>>> head = augment_source(normalized, resolved)
>>> head.source_type  # the head is the latest rule
'reference_resolve'
>>> [(r["source_type"], r["rule_id"]) for r in lineage_history(head)]
[('normalize_material', 'material_lower'), ('reference_resolve', 'material_resolve')]
"""

from __future__ import annotations

import dataclasses
import json
from collections import defaultdict

import bloodline as bl
import bloodline.constants
import pandas as pd

__all__ = ["RuleRecord", "augment_source", "augment_lineage", "lineage_history"]

# The head Source carries the ordered lifecycle under this reserved metadata key.
LINEAGE_KEY = "lineage"
_LINEAGE_COLUMN = bl.constants.DATA_LINEAGE_COLUMN


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class RuleRecord:
    """One rule in a cell's lifecycle: which rule, which version, and its evidence.

    ``source_type`` is a ladder tier (a :class:`carbonara.rules.SourceType` value,
    §8.1). ``inputs`` and ``confidence`` are the light evidence a provenance drawer
    shows; the full per-run detail lives in the ledger (§8.2).
    """

    rule_id: str
    rule_version: str
    source_type: str
    inputs: dict[str, object] = dataclasses.field(default_factory=dict)
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize to the plain dict stored in the head Source's lineage list."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "source_type": self.source_type,
            "inputs": dict(self.inputs),
            "confidence": self.confidence,
        }


def _record_from_source(source: bl.Source) -> dict[str, object]:
    """Fold a prior head Source into a lifecycle record (its first entry)."""
    metadata = source.source_metadata
    return RuleRecord(
        rule_id=str(metadata.get("rule_id", "")),
        rule_version=str(metadata.get("rule_version", "")),
        source_type=str(source.source_type),
        inputs=dict(metadata.get("inputs", {})),  # type: ignore[arg-type]
        confidence=metadata.get("confidence"),  # type: ignore[arg-type]
    ).to_dict()


def lineage_history(source: bl.Source | dict[str, object] | None) -> list[dict[str, object]]:
    """Read a cell's ordered lifecycle (oldest first) from its head Source.

    Accepts a :class:`~bloodline.Source`, a ``data_lineage`` cell entry
    (``{source_type, source_metadata}``), or ``None`` for an unsourced cell.
    """
    metadata: dict[str, object] = {}
    if isinstance(source, bl.Source):
        metadata = source.source_metadata
    elif isinstance(source, dict):
        nested = source.get("source_metadata", {})
        metadata = nested if isinstance(nested, dict) else {}
    history = metadata.get(LINEAGE_KEY, [])
    return [dict(entry) for entry in history] if isinstance(history, list) else []


def augment_source(prior: bl.Source | None, record: RuleRecord) -> bl.Source:
    """Head Source that appends ``record`` to ``prior``'s lifecycle, preserving it.

    The first augmentation seeds the list from ``prior`` (the original rule becomes
    the oldest entry); a ``None`` or unsourced ``prior`` yields a single-entry list.
    The returned Source's ``source_type`` is ``record``'s, so the head stays the
    latest rule.
    """
    if prior is None:
        history: list[dict[str, object]] = []
    elif LINEAGE_KEY in prior.source_metadata:
        history = [dict(entry) for entry in prior.source_metadata[LINEAGE_KEY]]  # type: ignore[union-attr]
    else:
        history = [_record_from_source(prior)]
    history.append(record.to_dict())
    return bl.Source(
        source_type=record.source_type,
        source_metadata={
            "rule_id": record.rule_id,
            "rule_version": record.rule_version,
            LINEAGE_KEY: history,
        },
    )


def _head_source(cell: object) -> bl.Source | None:
    """The current head Source for a column from a ``data_lineage`` cell, or None."""
    if not isinstance(cell, dict):
        return None
    payload = cell
    if "source_type" not in payload:
        return None
    return bl.Source.from_dict(payload)


def augment_lineage(
    frame: pd.DataFrame,
    *,
    record: RuleRecord,
    row_mask: pd.Series,
    column: str,
) -> pd.DataFrame:
    """Attach ``record`` to ``column``'s masked cells, preserving each prior lineage.

    Reads each masked cell's prior head Source, groups the rows that share a prior,
    and writes one augmented Source per group through ``apply_data_lineage`` with
    ``override=True``. Groups are applied in sorted order, so the result is
    byte-identical across runs regardless of row or dict order. Returns a new frame.
    """
    result = frame.copy()
    lineage = result.get(_LINEAGE_COLUMN)

    groups: dict[str, tuple[bl.Source | None, list[int]]] = defaultdict(lambda: (None, []))
    for position in result.loc[row_mask].index:
        cell = lineage[position] if lineage is not None else None
        prior = _head_source(cell.get(column) if isinstance(cell, dict) else None)
        key = json.dumps(prior.to_dict() if prior else None, sort_keys=True, default=str)
        groups[key] = (prior, groups[key][1] + [position])

    for key in sorted(groups):
        prior, positions = groups[key]
        group_mask = pd.Series(result.index.isin(positions), index=result.index)
        result = bl.apply_data_lineage(
            table=result,
            default_source=augment_source(prior, record),
            row_mask=group_mask,
            column_names=[column],
            override=True,
        )
    return result
