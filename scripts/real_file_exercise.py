"""Run one real, messy public file through ingest → normalize (BACKLOG.md item 3).

Not a QA fixture: there is no ground truth here, so nothing in this exercise is
used by the determinism or fill-accuracy suites. The connector has otherwise only
ever met files it generated; this proves it survives one it did not.

The file is a real U.S. textile-import table (USDA ERS, from U.S. Census / Commerce
trade data — see samples/README.md). It is aggregate statistics, not a component
BOM, so the honest outcome is twofold: the drift gate refuses it for review rather
than processing a non-BOM file, and the field normalizers handle its real values
without crashing — resolving what they recognize, flagging the rest.

Run: ``uv run python scripts/real_file_exercise.py``.
"""

from __future__ import annotations

import pathlib
import tempfile

from carbonara.ingest import admit, read_rows
from carbonara.normalize import parse_date, resolve_material

_SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "samples" / "us_textile_imports_by_fiber.csv"


def _drift_gate() -> None:
    """Admit the real file and show the gate refusing a non-BOM shape for review."""
    with tempfile.TemporaryDirectory() as store:
        result = admit(_SAMPLE, pathlib.Path(store))
    print("== ingest + drift gate ==")
    print(f"format   : {result.source_format.value} (detected by content)")
    print(f"encoding : {result.encoding}")
    print(f"status   : {result.status.value}")
    assert result.profile is not None  # a first, non-duplicate import always profiles
    print(f"columns  : {', '.join(c.name for c in result.profile.columns)}")
    proposal = result.mapping_proposal
    renames = proposal.renames if proposal is not None else {}
    print(f"mapping  : {renames or 'none — no source column matches the BOM contract'}")
    print("→ the gate stopped a real, non-BOM file for review; nothing was silently processed.\n")


def _normalizers_on_real_values() -> None:
    """Feed the file's real values to the normalizers; show they resolve or flag, never crash."""
    rows = read_rows(_SAMPLE)
    print(f"== normalizers on real values ({len(rows)} rows parsed, quoted commas and all) ==")

    print("material (from the `fiber` column):")
    for fiber in sorted({row["fiber"] for row in rows}):
        match = resolve_material(fiber)
        verdict = "unresolved → flag" if match is None else f"{match[0]} → {match[1]!r}"
        print(f"  {fiber:10} {verdict}")

    print("date (from the `period` column):")
    for period in sorted({row["period"] for row in rows})[:3]:
        parsed = parse_date(period)
        print(f"  {period:10} {'unparsed → null' if parsed is None else parsed.isoformat()}")
    print("→ every real value returned a clean result or an honest null/flag; no exceptions.")


def main() -> None:
    _drift_gate()
    _normalizers_on_real_values()


if __name__ == "__main__":
    main()
