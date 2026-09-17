"""Contract shape: the canonical fields in order, the quality_status vocabulary, immutability."""

from __future__ import annotations

import dataclasses

import pytest

from carbonara.contract import CANONICAL_COLUMNS, CanonicalRecord, QualityStatus


def test_canonical_columns_are_the_spec_order() -> None:
    assert CANONICAL_COLUMNS == (
        "record_id",
        "source_row_id",
        "style_id",
        "category",
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


def test_record_fields_match_canonical_column_order() -> None:
    field_names = tuple(f.name for f in dataclasses.fields(CanonicalRecord))
    assert field_names == CANONICAL_COLUMNS


def test_quality_status_is_the_fixed_set() -> None:
    assert {s.value for s in QualityStatus} == {
        "ok",
        "review_required",
        "action_required",
        "flagged",
    }


def test_record_is_immutable() -> None:
    rec = CanonicalRecord(
        record_id="r0001",
        source_row_id="7",
        style_id="TSH-001",
        category="TSH",
        sku="TSH-001-BLK-M",
        component="shell fabric",
        material_raw="Organic cottn",
        supplier_raw="Acme Textiles Ltd.",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.material_normalized = "cotton"  # ty: ignore[invalid-assignment]
