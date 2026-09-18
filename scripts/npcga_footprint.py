"""Real-data footprint: run the NPCGA garment dataset through the full pipeline.

Item 3's search found real apparel data — NPCGA, Norwegian post-consumer garments
(CC BY-SA 4.0, `samples/npcga_subset.csv`) — with real fibre composition and weight
in grams, blocked only by its semicolon delimiter. With that reader in place (item
7), this maps the file's real columns to the BOM contract and runs the full pipeline
(ingest → normalize → fill → footprint), producing a real material-stage footprint
from real fibre and weight data. It is an exercise (lives in `scripts/`, no ground
truth), not a QA fixture.

The mapping is the reviewer step a real import needs: the fibre column becomes the
material, the gram weight is annotated with its unit, and a row id and a single
`garment` component are assigned. Whatever the connector cannot resolve — a fibre
absent from the factor table (`wool`, `polyamide or nylon`), an ISO-3 country code
the name lookup does not know, a blank fibre stored as ``NaN`` — is flagged, never
guessed.

Run: ``uv run python scripts/npcga_footprint.py``.
"""

from __future__ import annotations

import pathlib
import tempfile

from carbonara.footprint import by_material, summarize
from carbonara.ingest import admit, read_rows
from carbonara.pipeline import run

_SUBSET = pathlib.Path(__file__).resolve().parent.parent / "samples" / "npcga_subset.csv"


def _bom_rows(npcga: list[dict[str, str]]) -> list[dict[str, str]]:
    """Map NPCGA's real columns to the BOM contract — the reviewer's mapping step."""
    rows: list[dict[str, str]] = []
    for position, source in enumerate(npcga):
        clean = {key.lstrip("﻿"): value for key, value in source.items()}  # the file carries a BOM
        grams = clean.get("Weight [gram]", "").strip()
        garment_id = clean.get("ID (AXXXX)", "")
        rows.append(
            {
                "source_row_id": str(position),
                "style_id": garment_id,
                "sku": garment_id,
                "component": "garment",
                "material": clean.get("Fibre 1 Layer 1", ""),
                "composition": "",
                "net_weight": f"{grams} g" if grams else "",  # the column header declares the unit
                "supplier": clean.get("Company/brand", ""),
                "country": clean.get("Made in", ""),
                "order_date": "",
                "quantity": "",
                "unit_price": "",
            }
        )
    return rows


def main() -> None:
    npcga = read_rows(_SUBSET)
    with tempfile.TemporaryDirectory() as store:
        admitted = admit(_SUBSET, pathlib.Path(store))
    columns = len(admitted.profile.columns) if admitted.profile is not None else 0
    print("== ingest (semicolon-delimited European file) ==")
    print(f"rows {len(npcga)}, columns {columns}, drift-gate status {admitted.status.value}")
    print("→ the file parses into its real columns; the reviewer then maps them.\n")

    result = run(_bom_rows(npcga), {}, content_hash="npcga_subset", created_at="2026-01-01T00:00:00Z")
    summary = summarize(result.footprint)
    low, high = summary.uncertainty_kgco2e
    print("== footprint (material stage, real fibre × real grams) ==")
    print(
        f"costed {summary.costed_n} / {len(npcga)} garments · "
        f"{summary.unmapped_n} unmapped material · {summary.no_weight_n} no weight"
    )
    print(
        f"total {summary.total_kgco2e:.1f} kgCO2e (range {low:.1f}–{high:.1f}); observed {summary.observed_share:.0%}"
    )
    print("by material:")
    for breakdown in by_material(result.footprint):
        print(f"  {breakdown.key:12} {breakdown.total_kgco2e:8.1f} kgCO2e  ({breakdown.costed_n} garments)")
    print("→ real materials × real grams = a real footprint; unknown fibres and ISO-3 countries are flagged.")


if __name__ == "__main__":
    main()
