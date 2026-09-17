"""Load the versioned reference vocabularies the connector resolves against.

Each vocabulary is a small in-repo CSV with a citation per row (``references/``),
so every resolved value stays auditable and reproducible.
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import pathlib

__all__ = ["MaterialVocab", "country_iso", "material_vocab", "supplier_names"]

_REFERENCES_DIR = pathlib.Path(__file__).resolve().parent.parent / "references"


def _read(name: str) -> list[dict[str, str]]:
    with (_REFERENCES_DIR / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


@functools.cache
def country_iso() -> dict[str, str]:
    """Map a lowercased country name to its ISO-3166 alpha-2 code."""
    return {row["name"].lower(): row["iso_alpha2"] for row in _read("countries_iso_v1.csv")}


@functools.cache
def supplier_names() -> tuple[str, ...]:
    """The canonical supplier names, in file order (a fuzzy-match tie-break is stable)."""
    return tuple(row["canonical"] for row in _read("suppliers_v1.csv"))


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class MaterialVocab:
    """The material vocabulary: canonical names and their shorthand codes."""

    canonical: tuple[str, ...]
    code_to_canonical: dict[str, str]


@functools.cache
def material_vocab() -> MaterialVocab:
    """Canonical materials in file order, plus the shorthand codes (``CO → cotton``)."""
    rows = _read("materials_v1.csv")
    return MaterialVocab(
        canonical=tuple(row["canonical"] for row in rows),
        code_to_canonical={row["code"]: row["canonical"] for row in rows if row["code"]},
    )
