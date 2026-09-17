"""Value normalizers: dates, weights→grams, composition parse + canonical form."""

from __future__ import annotations

from carbonara.normalize import format_composition, parse_composition, parse_date, parse_weight


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
