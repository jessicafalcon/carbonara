"""Canonical records are built with deterministic ids, raw fields set, normalized null."""

from __future__ import annotations

import pytest

from carbonara.materialize import SourceSchemaError, materialize


def _row(source_row_id: str, **over: str) -> dict[str, str]:
    row = {
        "source_row_id": source_row_id,
        "style_id": "TSH-1",
        "sku": "SKU",
        "component": "shell",
        "material": "cotton",
        "vendor": "Acme Textiles",
    }
    row.update(over)
    return row


def test_record_id_is_zero_padded_from_source_row_id():
    [sr] = materialize([_row("42")], {"vendor": "supplier"})
    assert sr.record.record_id == "r0042"
    assert sr.raw["supplier"] == "Acme Textiles"  # mapping applied to raw


def test_raw_fields_set_normalized_left_null():
    [sr] = materialize([_row("1")], {"vendor": "supplier"})
    assert sr.record.material_raw == "cotton"
    assert sr.record.material_normalized is None
    assert sr.record.component_weight_g is None
    assert sr.record.factory_country_iso is None


def test_category_is_derived_from_style_id():
    # The archetype the fill ladder backs off across (§7.6), resolved once here.
    [sr] = materialize([_row("1", style_id="DRS-12")], {"vendor": "supplier"})
    assert sr.record.category == "DRS"


def test_materialize_is_deterministic():
    rows = [_row("3"), _row("1"), _row("2")]
    first = materialize(rows, {"vendor": "supplier"})
    second = materialize(rows, {"vendor": "supplier"})
    assert [sr.record for sr in first] == [sr.record for sr in second]


def test_missing_required_column_names_the_column():
    row = _row("1")
    del row["vendor"]  # supplier is then absent after mapping
    with pytest.raises(SourceSchemaError, match="supplier"):
        materialize([row], {"vendor": "supplier"})


def test_non_integer_source_row_id_is_a_clear_error():
    with pytest.raises(SourceSchemaError, match="source_row_id must be an integer"):
        materialize([_row("R-001")], {"vendor": "supplier"})
