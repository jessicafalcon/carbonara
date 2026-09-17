"""Run each BOM vintage through the connector and stage its per-line footprints.

The staging table is the DAG's source: one row per *costed* component line, with
the production mass and factor the mart aggregates into a production-weighted
catalog total (brief §9). Only ``COSTED`` lines contribute to the headline total,
so unmapped, weightless and flagged lines are dropped here exactly as they are in
the Phase-5 catalog total.
"""

from __future__ import annotations

import csv
import dataclasses
import pathlib

import duckdb
import pandas as pd

from carbonara.footprint import FootprintStatus
from carbonara.ingest import content_hash
from carbonara.pipeline import PipelineResult, run

__all__ = ["VintageSpec", "VINTAGES", "footprint_lines", "stage_footprint_lines", "STAGING_TABLE"]

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FIXTURES = _ROOT / "fixtures"
_MAPPING = {"vendor": "supplier"}
#: Injected, not wall-clock — keeps the run id and ledger byte-reproducible.
_CREATED_AT = "2026-01-01T00:00:00Z"

#: The staging table the Lea DAG reads from.
STAGING_TABLE = "stg_footprint_lines"

#: The per-line staging schema, in fixed order for a stable frame.
_LINE_COLUMNS = ("vintage", "record_id", "material", "quantity", "weight_kg", "factor", "mass_kg", "footprint_kgco2e")


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class VintageSpec:
    """One vintage: its BOM file and the factor version its footprint is costed at."""

    label: str
    bom: str
    factor_version: str


VINTAGES: tuple[VintageSpec, ...] = (
    VintageSpec(label="v1", bom="bom_v1.csv", factor_version="v1"),
    VintageSpec(label="v2", bom="bom_v2.csv", factor_version="v2"),
)


def _run(spec: VintageSpec) -> PipelineResult:
    """Run the full connector over one vintage's BOM at its factor version."""
    path = _FIXTURES / spec.bom
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return run(
        rows,
        _MAPPING,
        content_hash=content_hash(path.read_bytes()),
        created_at=_CREATED_AT,
        factor_version=spec.factor_version,
    )


def footprint_lines(specs: tuple[VintageSpec, ...] = VINTAGES) -> pd.DataFrame:
    """Per-costed-line production footprints across the given vintages.

    One row per costed component line: ``mass_kg = quantity × weight_kg`` (the
    decomposition's volume/mix count) and ``factor`` (its intensity), so
    ``footprint_kgco2e = mass_kg × factor``. Ordered by ``(vintage, record_id)``
    for a deterministic frame.
    """
    records: list[dict[str, object]] = []
    for spec in specs:
        result = _run(spec)
        quantities = {source.record.record_id: source.record.quantity for source in result.records}
        for component in result.footprint.components:
            if component.status is not FootprintStatus.COSTED:
                continue
            quantity = quantities[component.record_id]
            if quantity is None or component.weight_g is None or component.factor_kgco2e_per_kg is None:
                continue
            mass_kg = quantity * component.weight_g / 1000
            records.append(
                {
                    "vintage": spec.label,
                    "record_id": component.record_id,
                    "material": component.material,
                    "quantity": quantity,
                    "weight_kg": component.weight_g / 1000,
                    "factor": component.factor_kgco2e_per_kg,
                    "mass_kg": mass_kg,
                    "footprint_kgco2e": mass_kg * component.factor_kgco2e_per_kg,
                }
            )
    frame = pd.DataFrame.from_records(records, columns=list(_LINE_COLUMNS))
    # record_id is zero-padded (``r0001``…), so a lexical sort is the numeric order.
    return frame.sort_values(["vintage", "record_id"]).reset_index(drop=True)


def stage_footprint_lines(con: duckdb.DuckDBPyConnection, specs: tuple[VintageSpec, ...] = VINTAGES) -> pd.DataFrame:
    """Register the per-line footprints as the DuckDB staging table and return them."""
    lines = footprint_lines(specs)
    con.register("_lines_frame", lines)
    con.execute(f"CREATE OR REPLACE TABLE {STAGING_TABLE} AS SELECT * FROM _lines_frame")
    con.unregister("_lines_frame")
    return lines
