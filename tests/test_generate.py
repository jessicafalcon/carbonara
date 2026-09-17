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


FIXTURE_FILES = (
    "bom_v1.csv",
    "ground_truth_v1.csv",
    "bom_v2.csv",
    "ground_truth_v2.csv",
    "decomposition_truth.csv",
)

TSH_SHELL_SHIFT_STYLES = {f"TSH-{index:02d}" for index in range(1, 7)}
VOLUME_MULT = {"TSH": 1.20, "HOO": 1.10, "TRO": 0.90, "DRS": 0.85}


def test_regeneration_is_byte_identical(tmp_path: pathlib.Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    generate.write_fixtures(first)
    generate.write_fixtures(second)
    for name in FIXTURE_FILES:
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


# --- Two vintages (brief §6) ------------------------------------------------


def test_v2_plants_the_same_cases_as_v1() -> None:
    # Planting runs on the untransformed rows, so both vintages plant every case.
    _, ground_truth = generate.generate(vintage=generate.V2)
    assert {row["case"] for row in ground_truth} == EXPECTED_CASES


def test_v2_corrupts_exactly_the_same_cells_as_v1() -> None:
    # The reorder (plant before transform) makes the corruption layout identical
    # across vintages, so fill error cancels in the v1→v2 delta.
    _, gt1 = generate.generate(vintage=generate.V1)
    _, gt2 = generate.generate(vintage=generate.V2)
    cells = lambda gt: {(row["source_row_id"], row["column"], row["case"]) for row in gt}  # noqa: E731
    assert cells(gt1) == cells(gt2)


def test_v2_volume_multiplier_scales_quantity() -> None:
    v1_rows, _ = generate.generate(vintage=generate.V1)
    v2_rows, _ = generate.generate(vintage=generate.V2)
    v1_by_id = {row["source_row_id"]: row for row in v1_rows}
    # Identical planting means every v2 line maps to its v1 twin by id and style.
    for row in v2_rows:
        origin = v1_by_id[row["source_row_id"]]
        code = row["style_id"].split("-")[0]
        assert int(row["quantity"]) == round(int(origin["quantity"]) * VOLUME_MULT[code])


def test_v2_mix_shift_moves_named_lines_to_organic_cotton() -> None:
    rows, _ = generate.generate(vintage=generate.V2)
    shifted = [r for r in rows if r["style_id"] in TSH_SHELL_SHIFT_STYLES and r["component"] == "shell fabric"]
    assert len(shifted) == len(TSH_SHELL_SHIFT_STYLES)
    for row in shifted:
        assert row["material"] == "organic cotton"
        assert row["composition"] == "100% organic cotton"


def test_decomposition_truth_isolates_the_planted_changes() -> None:
    footprint: dict[str, dict[str, float]] = {"v1": {}, "v2": {}}
    factor: dict[str, dict[str, float]] = {"v1": {}, "v2": {}}
    for vintage in (generate.V1, generate.V2):
        for row in generate.truth_basis(vintage):
            material = row["material"]
            footprint[vintage.label][material] = float(row["true_footprint_kgco2e"])
            factor[vintage.label][material] = float(row["factor_kgco2e_per_kg"])
    # The material-mix shift shows up as organic cotton appearing only in v2.
    assert "organic cotton" not in footprint["v1"]
    assert footprint["v2"]["organic cotton"] > 0
    # The factor bump is planted on polyester alone: every other shared material
    # keeps its v1 factor, so the intensity effect is isolable.
    shared = footprint["v1"].keys() & footprint["v2"].keys()
    assert {m for m in shared if factor["v2"][m] != factor["v1"][m]} == {"polyester"}
    # Every material carries a positive footprint, and the catalog total moves.
    assert all(value > 0 for basket in footprint.values() for value in basket.values())
    delta = sum(footprint["v2"].values()) - sum(footprint["v1"].values())
    assert abs(delta) > 1.0
