"""Build canonical records from an accepted import and its confirmed column mapping."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from carbonara.contract import CanonicalRecord

__all__ = ["SourceRecord", "materialize"]


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
    for row in rows:
        raw = _apply_mapping(row, mapping)
        record = CanonicalRecord(
            record_id=f"r{int(raw['source_row_id']):04d}",
            source_row_id=raw["source_row_id"],
            style_id=raw["style_id"],
            sku=raw["sku"],
            component=raw["component"],
            material_raw=raw["material"],
            supplier_raw=raw["supplier"],
        )
        materialized.append(SourceRecord(record=record, raw=raw))
    return materialized
