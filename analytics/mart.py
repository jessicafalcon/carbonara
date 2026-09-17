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

__all__ = ["MODELS", "MART_TABLE", "build_mart", "footprint_mart"]

_DAG_DIR = pathlib.Path(__file__).resolve().parent / "dag"

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
