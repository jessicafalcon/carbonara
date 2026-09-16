"""The canonical BOM record: the frozen contract every later phase writes and reads."""

from __future__ import annotations

import dataclasses
import datetime
import enum

__all__ = ["CANONICAL_COLUMNS", "CanonicalRecord", "QualityStatus"]


class QualityStatus(enum.StrEnum):
    """Where a record lands after processing — the fixed vocabulary of outcomes.

    Grounded in the brief: a schema-drift or uncertain mapping needs review
    (§12), the fill ladder's honest last resort is ``action required`` (§7.4),
    and an anomaly or implausible value is flagged, never silently corrected
    (§7.3). ``OK`` is the clean default.

    >>> QualityStatus("review_required")
    <QualityStatus.REVIEW_REQUIRED: 'review_required'>
    """

    OK = "ok"
    REVIEW_REQUIRED = "review_required"
    ACTION_REQUIRED = "action_required"
    FLAGGED = "flagged"


#: The canonical record's columns, in serialization order (brief §6). Pinned to
#: the dataclass field order by ``tests/test_contract.py`` so the two can't drift.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "record_id",
    "source_row_id",
    "style_id",
    "sku",
    "component",
    "material_raw",
    "material_normalized",
    "composition",
    "component_weight_g",
    "supplier_raw",
    "supplier_normalized",
    "factory_country_iso",
    "order_date",
    "quantity",
    "unit_price",
    "quality_status",
)


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class CanonicalRecord:
    """One BOM component line: raw source values beside their normalized forms.

    Identity and raw fields are set at ingest; the normalized and parsed fields
    default to ``None`` and are populated as later rules run. The record is
    frozen — a rule never mutates it in place; it emits a new record and records
    the change in the ledger (governance, brief §8).

    >>> rec = CanonicalRecord(
    ...     record_id="r0001",
    ...     source_row_id="7",
    ...     style_id="TSH-001",
    ...     sku="TSH-001-BLK-M",
    ...     component="shell fabric",
    ...     material_raw="Organic cottn",
    ...     supplier_raw="Acme Textiles Ltd.",
    ... )
    >>> rec.material_normalized is None
    True
    >>> rec.quality_status
    <QualityStatus.OK: 'ok'>
    """

    record_id: str
    source_row_id: str
    style_id: str
    sku: str
    component: str
    material_raw: str
    material_normalized: str | None = None
    composition: str | None = None
    component_weight_g: float | None = None
    supplier_raw: str
    supplier_normalized: str | None = None
    factory_country_iso: str | None = None
    order_date: datetime.date | None = None
    quantity: int | None = None
    unit_price: float | None = None
    quality_status: QualityStatus = QualityStatus.OK
