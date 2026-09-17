"""Render the brand-facing view over the fixture BOM to a standalone HTML file.

Lives outside ``carbonara/`` because it does file I/O and picks an output path;
the render itself is deterministic (``carbonara.view.render_view``). The ledger
timestamp is injected as a fixed value so the page is byte-reproducible.

Run ``python scripts/build_view.py [output.html]`` (default ``build/view.html``).
"""

from __future__ import annotations

import csv
import pathlib
import sys

from carbonara.fill import fill_weights
from carbonara.footprint import factor_diff
from carbonara.ingest import content_hash
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records
from carbonara.pipeline import run
from carbonara.view import render_view

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_MAPPING = {"vendor": "supplier"}
_CREATED_AT = "2026-01-01T00:00:00Z"  # injected, not wall-clock — keeps the page reproducible


def main(out: pathlib.Path) -> None:
    with _BOM_V1.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    result = run(rows, _MAPPING, content_hash=content_hash(_BOM_V1.read_bytes()), created_at=_CREATED_AT)

    filled = fill_weights(normalize_records(materialize(rows, _MAPPING)).records)
    diff = factor_diff(filled.records, filled.events, from_version="v1", to_version="v2")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_view(result, diff=diff, title="carbonara"), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes) · run {result.run_id}")


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "build" / "view.html"
    main(target)
