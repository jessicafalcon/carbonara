"""Run the staging→core→mart DuckDB SQL DAG over the staged footprint lines.

A tiny layered SQL transformation (brief §11): staging types the raw lines, core
is the conformed per-line grain, and the mart aggregates to the production-weighted
catalog footprint by material × vintage — the basis the v1→v2 decomposition reads.
Plain ``.sql`` models run in dependency order; no orchestration framework.
"""

from __future__ import annotations

import pathlib

import duckdb
import pandas as pd

from analytics.vintages import VINTAGES, VintageSpec, load_raw_footprint_lines

__all__ = ["MODELS", "MART_TABLE", "MART_COLUMNS", "build_mart", "footprint_mart", "truth_mart"]

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DAG_DIR = pathlib.Path(__file__).resolve().parent / "dag"
_TRUTH_CSV = _ROOT / "fixtures" / "decomposition_truth.csv"

#: The mart schema the decomposition reads (count = mass_kg, fact = factor).
MART_COLUMNS = ("vintage", "material", "mass_kg", "factor", "footprint_kgco2e")

#: The DAG models, in dependency order (staging → core → mart).
MODELS = ("staging.sql", "core.sql", "mart.sql")

#: The mart table the decomposition reads.
MART_TABLE = "mart_footprint_by_material"


def build_mart(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run the DAG models in order against a connection holding the raw table."""
    for model in MODELS:
        con.execute((_DAG_DIR / model).read_text())
    return con.execute(f"SELECT * FROM {MART_TABLE} ORDER BY vintage, material").df()


def footprint_mart(specs: tuple[VintageSpec, ...] = VINTAGES) -> pd.DataFrame:
    """Stage both vintages and build the production-weighted mart end to end."""
    con = duckdb.connect()
    load_raw_footprint_lines(con, specs)
    return build_mart(con)


def truth_mart() -> pd.DataFrame:
    """The known-true mart from ``fixtures/decomposition_truth.csv``.

    The same shape as :func:`footprint_mart`, so the two feed the identical
    decomposition — the pipeline's explanation is validated against this one.
    """
    truth = pd.read_csv(_TRUTH_CSV).rename(
        columns={
            "true_mass_kg": "mass_kg",
            "factor_kgco2e_per_kg": "factor",
            "true_footprint_kgco2e": "footprint_kgco2e",
        }
    )
    return truth.loc[:, list(MART_COLUMNS)].sort_values(["vintage", "material"]).reset_index(drop=True)
