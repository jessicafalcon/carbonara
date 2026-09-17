"""Reference vocabularies load deterministically and cover the fixture's values."""

from __future__ import annotations

from carbonara.references import country_iso, material_vocab, supplier_names


def test_country_iso_covers_the_fixture_countries():
    countries = country_iso()
    assert countries["portugal"] == "PT"
    assert countries["vietnam"] == "VN"


def test_material_vocab_has_canonical_names_and_shorthand_codes():
    vocab = material_vocab()
    assert "organic cotton" in vocab.canonical
    assert vocab.code_to_canonical["CO"] == "cotton"
    assert vocab.code_to_canonical["PL"] == "polyester"


def test_supplier_names_are_the_canonical_entities():
    assert supplier_names() == (
        "Acme Textiles",
        "Bharat Mills",
        "Golden Thread",
        "Nordic Weave",
        "Oceanic Fabrics",
    )


def test_loads_are_stable():
    assert country_iso() == country_iso()
    assert material_vocab() == material_vocab()
