"""Attach Bloodline provenance to the canonical frame — the lineage spine (§8.1)."""

from __future__ import annotations

import dataclasses
from collections import defaultdict

import bloodline as bl
import pandas as pd

from carbonara.augment import RuleRecord, augment_lineage
from carbonara.contract import CANONICAL_COLUMNS
from carbonara.materialize import SourceRecord
from carbonara.rules import RuleEvent, SourceType

__all__ = ["apply_lineage", "to_frame"]


def to_frame(records: list[SourceRecord]) -> pd.DataFrame:
    """Build the canonical frame (CANONICAL_COLUMNS, in record order) from records."""
    rows = [dataclasses.asdict(source.record) for source in records]
    return pd.DataFrame(rows, columns=list(CANONICAL_COLUMNS))


def _apply_first_rules(frame: pd.DataFrame, events: list[RuleEvent]) -> pd.DataFrame:
    """Write each cell's first rule as a plain Bloodline Source (the head).

    One event per cell here (the caller passes the first rule of each cell), grouped
    by rule and applied in a sorted order so the head Source is deterministic.
    """
    groups: dict[tuple[str, SourceType, str, str], list[str]] = defaultdict(list)
    for event in events:
        groups[(event.column, event.source_type, event.rule_id, event.rule_version)].append(event.record_id)

    result = frame
    for (column, source_type, rule_id, version), record_ids in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][2])
    ):
        mask = result["record_id"].isin(record_ids)
        result = bl.apply_data_lineage(
            table=result,
            default_source=bl.Source(
                source_type=source_type.value,
                source_metadata={"rule_id": rule_id, "rule_version": version},
            ),
            row_mask=mask,
            column_names=[column],
            override=True,
        )
    return result


def _record_from_event(event: RuleEvent) -> RuleRecord:
    """A lifecycle record for a rule chained onto an already-sourced cell."""
    return RuleRecord(
        rule_id=event.rule_id,
        rule_version=event.rule_version,
        source_type=event.source_type.value,
        inputs=dict(event.method_params),
    )


def apply_lineage(frame: pd.DataFrame, events: list[RuleEvent]) -> pd.DataFrame:
    """Tag each touched cell with its rule lineage, chaining a cell's later rules (§8.1).

    A cell's first rule writes a plain Bloodline Source (the head, current value +
    light metadata); any further rule on the same cell chains onto it via
    :func:`carbonara.augment.augment_lineage`, so the spine carries the ordered
    lifecycle instead of the last write clobbering it — matching the ledger, which
    records every rule (§8.2). A cell touched by exactly one rule is byte-identical
    to a plain single-Source write. Cells and rule groups are applied in a sorted
    order so the ``data_lineage`` column is deterministic across runs.

    A null cell carries no value, so Bloodline leaves it unsourced (``{}``) — honest
    by construction; its ``action_required`` verdict lives on the record's
    ``quality_status`` and in the ledger, not as a lineage source on an absent value.
    """
    by_cell: dict[tuple[str, str], list[RuleEvent]] = defaultdict(list)
    for event in events:
        by_cell[(event.record_id, event.column)].append(event)

    result = _apply_first_rules(frame, [cell_events[0] for cell_events in by_cell.values()])

    # ponytail: a cell's further rules are chained one at a time per cell — no live
    # cell reaches here today (one rule per cell), and the approval re-apply chains
    # its own; group by (rule, depth) if a multi-rule tier makes this a hot path.
    for record_id, column in sorted(by_cell):
        for event in by_cell[(record_id, column)][1:]:
            result = augment_lineage(
                result,
                record=_record_from_event(event),
                row_mask=result["record_id"] == record_id,
                column=column,
            )
    return result
