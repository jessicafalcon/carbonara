"""Phase-6 analytics layer: staging the two vintages' per-line footprints."""

from __future__ import annotations

import duckdb
import pandas as pd

from analytics.vintages import STAGING_TABLE, footprint_lines, stage_footprint_lines


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


def test_staging_table_matches_the_frame() -> None:
    con = duckdb.connect()
    lines = stage_footprint_lines(con)
    row = con.execute(f"SELECT count(*) FROM {STAGING_TABLE}").fetchone()
    assert row is not None
    assert row[0] == len(lines)
