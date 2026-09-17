"""Value normalizers: dates, weights→grams, composition parse + canonical form."""

from __future__ import annotations

from carbonara.materialize import materialize
from carbonara.normalize import (
    format_composition,
    normalize_records,
    parse_composition,
    parse_date,
    parse_weight,
    resolve_material,
    resolve_supplier,
)
from carbonara.rules import AnomalyCategory, SourceType


def test_mixed_units_convert_to_grams():
    assert parse_weight("0.42 kg") == 420.0
    assert parse_weight("492 g") == 492.0


def test_malformed_dates_return_none():
    assert parse_date("2024-13-07") is None
    assert parse_date("2024/02/31") is None
    assert parse_date("2024-01-08") is not None


def test_shorthand_composition_expands_codes_and_canonicalizes():
    pairs = parse_composition("70/30 CO/PL")
    assert pairs is not None
    assert pairs == [(0.7, "cotton"), (0.3, "polyester")]
    assert format_composition(pairs) == "70% cotton / 30% polyester"


def test_composition_sum_is_available_for_validation():
    pairs = parse_composition("95% cotton / 5% elastane")
    assert pairs is not None
    assert round(sum(fraction for fraction, _ in pairs), 6) == 1.0


def test_unparseable_composition_is_none():
    assert parse_composition("mostly cotton") is None


def test_supplier_variants_resolve_above_threshold():
    for spelling in ("ACME TEXTILES", "Acme Textiles Ltd.", "acme textiles ltd"):
        match = resolve_supplier(spelling)
        assert match is not None and match[0] == "Acme Textiles"


def test_material_typo_is_a_proposal_not_applied():
    assert resolve_material("Organic cottn") == ("proposal", "organic cotton")
    assert resolve_material("cotton") == ("exact", "cotton")


def _source(**over: str):
    row = {
        "source_row_id": "1",
        "style_id": "S",
        "sku": "K",
        "component": "shell",
        "material": "cotton",
        "vendor": "Acme Textiles Ltd.",
        "composition": "70/30 CO/PL",
        "net_weight": "0.42 kg",
        "country": "Portugal",
        "order_date": "2024-01-08",
        "quantity": "10",
        "unit_price": "5.0",
    }
    row.update(over)
    return materialize([row], {"vendor": "supplier"})


def test_pass_normalizes_and_records_events():
    result = normalize_records(_source())
    record = result.records[0].record
    assert record.component_weight_g == 420.0
    assert record.composition == "70% cotton / 30% polyester"
    assert record.factory_country_iso == "PT"
    assert record.supplier_normalized == "Acme Textiles"
    assert record.quantity == 10 and record.unit_price == 5.0
    types = {event.source_type for event in result.events}
    assert SourceType.NORMALIZE_UNIT in types
    assert SourceType.NORMALIZE_SUPPLIER in types


def test_pass_emits_material_proposal_finding_without_editing():
    result = normalize_records(_source(material="Organic cottn"))
    assert result.records[0].record.material_normalized is None
    [finding] = [f for f in result.findings if f.category is AnomalyCategory.MAPPING]
    assert finding.proposed_value == "organic cotton"


def test_pass_is_deterministic():
    assert normalize_records(_source()).events == normalize_records(_source()).events
