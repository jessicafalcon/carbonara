"""Material factors load, cover every fixture material, and carry a citation."""

from __future__ import annotations

from carbonara.references import material_factors, material_vocab


def test_every_vocabulary_material_has_a_factor():
    factors = material_factors()
    for material in material_vocab().canonical:
        assert material in factors, material


def test_factors_are_positive_and_cited():
    for material, factor in material_factors().items():
        assert factor.factor_kgco2e_per_kg > 0, material
        assert factor.source and factor.source_version and factor.source_ref, material


def test_organic_cotton_is_lower_than_conventional_cotton():
    factors = material_factors()
    assert factors["organic cotton"].factor_kgco2e_per_kg < factors["cotton"].factor_kgco2e_per_kg
