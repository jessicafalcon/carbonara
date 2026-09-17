"""The append-only rule-event ledger: the ordered history of every rule application."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterable

from carbonara.rules import RuleEvent, SourceType

__all__ = ["Ledger", "LedgerRow", "run_id_for"]


def run_id_for(content_hash: str, ruleset_version: str) -> str:
    """A deterministic run id from the input hash and ruleset version (no uuid, no clock)."""
    return hashlib.sha256(f"{content_hash}:{ruleset_version}".encode()).hexdigest()[:16]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class LedgerRow:
    """One ledger row — the §8.2 schema. Built from a RuleEvent plus run context.

    ``created_at`` is injected by the caller, never read from the clock inside the
    data path, so a re-run with the same inputs reproduces the ledger exactly.
    """

    event_id: str
    run_id: str
    record_id: str
    column: str
    rule_id: str
    rule_version: str
    source_type: SourceType
    method_params: dict[str, object]
    value_before: str | None
    value_after: str | None
    is_original_null: bool
    uncertainty_range: tuple[float, float] | None
    created_at: str

    @classmethod
    def from_event(cls, event: RuleEvent, *, run_id: str, created_at: str) -> LedgerRow:
        """Promote a RuleEvent to a ledger row under a run."""
        return cls(
            event_id=event.event_id,
            run_id=run_id,
            record_id=event.record_id,
            column=event.column,
            rule_id=event.rule_id,
            rule_version=event.rule_version,
            source_type=event.source_type,
            method_params=event.method_params,
            value_before=event.value_before,
            value_after=event.value_after,
            is_original_null=event.is_original_null,
            uncertainty_range=event.uncertainty_range,
            created_at=created_at,
        )

    def as_dict(self) -> dict[str, object]:
        """A JSON-friendly, deterministically-ordered row for serialization or query."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "record_id": self.record_id,
            "column": self.column,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "source_type": self.source_type.value,
            "method_params": json.dumps(self.method_params, sort_keys=True),
            "value_before": self.value_before,
            "value_after": self.value_after,
            "is_original_null": self.is_original_null,
            "uncertainty_range": list(self.uncertainty_range) if self.uncertainty_range else None,
            "created_at": self.created_at,
        }


class Ledger:
    """An append-only store of rule events, in application order."""

    def __init__(self) -> None:
        self._rows: list[LedgerRow] = []

    def extend(self, events: Iterable[RuleEvent], *, run_id: str, created_at: str) -> None:
        """Append events as ledger rows under one run."""
        self._rows.extend(LedgerRow.from_event(event, run_id=run_id, created_at=created_at) for event in events)

    def rows(self) -> tuple[LedgerRow, ...]:
        """Every row, in append order."""
        return tuple(self._rows)

    def for_record(self, record_id: str) -> tuple[LedgerRow, ...]:
        """The rows touching one record — what the provenance drawer reads."""
        return tuple(row for row in self._rows if row.record_id == record_id)

    def to_jsonl(self) -> str:
        """Serialize the ledger as deterministic JSON lines."""
        return "\n".join(json.dumps(row.as_dict(), sort_keys=True) for row in self._rows)
