"""Attach Bloodline provenance to the canonical frame — the lineage spine (§8.1)."""

from __future__ import annotations

import dataclasses
from collections import defaultdict

import bloodline as bl
import pandas as pd

from carbonara.contract import CANONICAL_COLUMNS
from carbonara.materialize import SourceRecord
from carbonara.rules import RuleEvent, SourceType

__all__ = ["apply_lineage", "to_frame"]


def to_frame(records: list[SourceRecord]) -> pd.DataFrame:
    """Build the canonical frame (CANONICAL_COLUMNS, in record order) from records."""
    rows = [dataclasses.asdict(source.record) for source in records]
    return pd.DataFrame(rows, columns=list(CANONICAL_COLUMNS))


def apply_lineage(frame: pd.DataFrame, events: list[RuleEvent]) -> pd.DataFrame:
    """Tag each touched cell with a Bloodline Source, grouped by column and rule.

    Bloodline holds the *current* source per cell (source_type + light metadata);
    the per-row detail lives in the ledger (§8.2). Groups are applied in a sorted
    order so the resulting ``data_lineage`` column is deterministic.
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

    # A null cell carries no value, so Bloodline leaves it unsourced ({}) — honest
    # by construction. The action_required verdict lives on the record's
    # quality_status and in the ledger, not as a lineage source on an absent value.
    return result
