"""Build canonical records from an accepted import and its confirmed column mapping."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from carbonara.contract import CanonicalRecord

__all__ = ["SourceRecord", "SourceSchemaError", "materialize"]

#: Source columns materialize needs present (post-mapping) to build a record.
_REQUIRED_COLUMNS = ("source_row_id", "style_id", "sku", "component", "material", "supplier")


class SourceSchemaError(Exception):
    """A mapped source row is missing a required column or has a malformed key field.

    Raised at the materialize boundary so a structural mismatch — a mapping that
    dropped a column, a non-integer ``source_row_id`` — fails with a named cause
    instead of a raw ``KeyError``/``ValueError``. The drift gate is the designed
    place to catch a missing column (``REVIEW_REQUIRED``); this is the backstop.
    """


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class SourceRecord:
    """A canonical record beside its raw source row.

    The record holds only identity and raw-passthrough fields at this stage
    (normalized fields are ``None``); ``raw`` keeps the full source row under
    canonical source names, so every normalization can cite the value it replaced.
    """

    record: CanonicalRecord
    raw: dict[str, str]


def _apply_mapping(row: Mapping[str, str], mapping: Mapping[str, str]) -> dict[str, str]:
    """Rename observed source headers to their confirmed canonical source names."""
    return {mapping.get(key, key): value for key, value in row.items()}


def materialize(rows: Sequence[Mapping[str, str]], mapping: Mapping[str, str]) -> list[SourceRecord]:
    """Turn accepted raw rows into canonical records, applying the confirmed mapping.

    ``record_id`` is derived from the source row id, so it is stable across runs
    (no counter, no clock). Raw source rows keyed by anything other than the
    expected source names must have been resolved by ``mapping`` first.

    >>> rows = [{"source_row_id": "7", "style_id": "TSH-1", "sku": "S", "component": "shell",
    ...          "material": "cotton", "vendor": "Acme"}]
    >>> [sr] = materialize(rows, {"vendor": "supplier"})
    >>> sr.record.record_id, sr.record.material_raw, sr.record.supplier_raw
    ('r0007', 'cotton', 'Acme')
    >>> sr.record.material_normalized is None
    True
    """
    materialized: list[SourceRecord] = []
    for position, row in enumerate(rows):
        raw = _apply_mapping(row, mapping)
        missing = [column for column in _REQUIRED_COLUMNS if column not in raw]
        if missing:
            raise SourceSchemaError(f"row {position}: missing required column(s) {missing}")
        try:
            row_number = int(raw["source_row_id"])
        except ValueError:
            raise SourceSchemaError(
                f"row {position}: source_row_id must be an integer, got {raw['source_row_id']!r}"
            ) from None
        record = CanonicalRecord(
            record_id=f"r{row_number:04d}",
            source_row_id=raw["source_row_id"],
            style_id=raw["style_id"],
            sku=raw["sku"],
            component=raw["component"],
            material_raw=raw["material"],
            supplier_raw=raw["supplier"],
        )
        materialized.append(SourceRecord(record=record, raw=raw))
    return materialized
