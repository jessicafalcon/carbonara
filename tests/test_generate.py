"""Fixture generator: determinism, planted-case coverage and labeling, missingness band."""

from __future__ import annotations

import pathlib

from carbonara.contract import CANONICAL_COLUMNS
from fixtures import generate

# Every case the generator plants — the §12 fixture-behavior rows plus the
# supplier-variant and missingness-band cases. Pinned so a dropped or renamed
# plant fails here.
EXPECTED_CASES = {
    "renamed_header",
    "supplier_variant",
    "material_typo",
    "composition_shorthand",
    "mixed_units_kg",
    "zero_weight_positive_value",
    "malformed_date",
    "extreme_price",
    "duplicate_key",
    "duplicate_file_upload",
    "factor_table_revision",
    "blank_weight_dense_tight",
    "blank_weight_high_spread",
    "blank_weight_sparse",
    "implausible_weight",
    "blank_weight",
}

# The fill-ladder branches and the outcome each planted group is meant to reach.
LADDER_EXPECTED = {
    "blank_weight_dense_tight": "GROUPED_MEDIAN fill",
    "blank_weight_high_spread": "fails dispersion -> reference constant",
    "blank_weight_sparse": "fails support -> reference constant",
    "implausible_weight": "trips plausibility band -> rejected/flagged",
}


def test_regeneration_is_byte_identical(tmp_path: pathlib.Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    generate.write_fixtures(first)
    generate.write_fixtures(second)
    for name in ("bom_v1.csv", "ground_truth_v1.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_every_planted_case_is_present() -> None:
    _, ground_truth = generate.generate()
    assert {row["case"] for row in ground_truth} == EXPECTED_CASES


def test_ladder_branches_labeled_with_expected_outcome() -> None:
    _, ground_truth = generate.generate()
    expected_by_case = {row["case"]: row["expected"] for row in ground_truth}
    for case, expected in LADDER_EXPECTED.items():
        assert expected_by_case[case] == expected


def test_missingness_band_within_target() -> None:
    rows, _ = generate.generate()
    blank = sum(1 for row in rows if row["net_weight"] == "")
    assert 0.30 <= blank / len(rows) <= 0.40


def test_every_blanked_weight_has_retained_truth() -> None:
    rows, ground_truth = generate.generate()
    retained = {row["source_row_id"] for row in ground_truth if row["column"] == "component_weight_g"}
    blanked = {row["source_row_id"] for row in rows if row["net_weight"] == ""}
    assert blanked <= retained


def test_row_level_ground_truth_targets_canonical_columns() -> None:
    _, ground_truth = generate.generate()
    for row in ground_truth:
        if row["source_row_id"] != "0":
            assert row["column"] in CANONICAL_COLUMNS


def test_renamed_header_is_emitted(tmp_path: pathlib.Path) -> None:
    generate.write_fixtures(tmp_path)
    header = (tmp_path / "bom_v1.csv").read_text().splitlines()[0].split(",")
    assert "vendor" in header
    assert "supplier" not in header
