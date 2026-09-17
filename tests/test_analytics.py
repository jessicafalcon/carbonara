"""Phase-6 analytics layer: staging the vintages and the staging→core→mart DAG."""

from __future__ import annotations

import duckdb
import pandas as pd

from analytics.mart import footprint_mart
from analytics.vintages import RAW_TABLE, footprint_lines, load_raw_footprint_lines


def test_footprint_lines_are_deterministic() -> None:
    pd.testing.assert_frame_equal(footprint_lines(), footprint_lines())


def test_footprint_lines_cover_both_vintages_and_only_costed_lines() -> None:
    lines = footprint_lines()
    assert set(lines["vintage"]) == {"v1", "v2"}
    # Every staged line is costed: non-negative mass/footprint (a zero-weight line
    # costs at zero) and a positive factor, with footprint = mass × factor.
    assert (lines["mass_kg"] >= 0).all()
    assert (lines["footprint_kgco2e"] >= 0).all()
    assert (lines["factor"] > 0).all()
    assert (lines["footprint_kgco2e"] - lines["mass_kg"] * lines["factor"]).abs().max() < 1e-9


def test_footprint_lines_show_the_material_mix_shift() -> None:
    lines = footprint_lines()
    v1_materials = set(lines.loc[lines["vintage"] == "v1", "material"])
    v2_materials = set(lines.loc[lines["vintage"] == "v2", "material"])
    assert "organic cotton" in v2_materials
    assert "organic cotton" not in v1_materials


def test_raw_table_matches_the_frame() -> None:
    con = duckdb.connect()
    lines = load_raw_footprint_lines(con)
    row = con.execute(f"SELECT count(*) FROM {RAW_TABLE}").fetchone()
    assert row is not None
    assert row[0] == len(lines)


# --- staging → core → mart DAG ----------------------------------------------


def test_mart_matches_the_python_reference_aggregate() -> None:
    mart = footprint_mart()
    reference = (
        footprint_lines()
        .groupby(["vintage", "material"], as_index=False)
        .agg(mass_kg=("mass_kg", "sum"), factor=("factor", "min"), footprint_kgco2e=("footprint_kgco2e", "sum"))
        .sort_values(["vintage", "material"])
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(mart, reference, check_exact=False, atol=1e-6)


def test_mart_is_reproducible() -> None:
    pd.testing.assert_frame_equal(footprint_mart(), footprint_mart())


def test_mart_is_one_row_per_vintage_material_with_the_mix_shift() -> None:
    mart = footprint_mart()
    assert not mart.duplicated(subset=["vintage", "material"]).any()
    v2 = mart[mart["vintage"] == "v2"]
    assert "organic cotton" in set(v2["material"])
    assert "organic cotton" not in set(mart.loc[mart["vintage"] == "v1", "material"])
