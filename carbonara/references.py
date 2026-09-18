"""Load the versioned reference vocabularies the connector resolves against.

Each vocabulary is a small in-repo CSV with a citation per row (``references/``),
so every resolved value stays auditable and reproducible.
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import hashlib
import pathlib

__all__ = [
    "MaterialFactor",
    "MaterialVocab",
    "ReferenceWeight",
    "country_iso",
    "factor_digest",
    "material_factors",
    "material_vocab",
    "reference_digest",
    "reference_weights",
    "supplier_names",
]

_REFERENCES_DIR = pathlib.Path(__file__).resolve().parent.parent / "references"

#: The reference vocabularies that feed a run, besides the versioned factor table.
#: Hashed into the run id so a change to any of them is a new, detectable run.
_RUN_REFERENCE_FILES = ("countries_iso_v1.csv", "materials_v1.csv", "suppliers_v1.csv", "reference_weights_v1.csv")


def _read(name: str) -> list[dict[str, str]]:
    with (_REFERENCES_DIR / name).open(newline="") as handle:
        return list(csv.DictReader(handle))


def _digest(names: tuple[str, ...]) -> str:
    """A content hash over the named reference files (order-independent, 16 hex)."""
    hasher = hashlib.sha256()
    for name in sorted(names):
        hasher.update(name.encode())
        hasher.update(b"\0")
        hasher.update((_REFERENCES_DIR / name).read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()[:16]


@functools.cache
def factor_digest(version: str = "v1") -> str:
    """Content hash of one factor table — its identity by bytes, not by filename."""
    return _digest((f"material_factors_{version}.csv",))


@functools.cache
def reference_digest(factor_version: str = "v1") -> str:
    """Content hash of every reference file a run reads (vocabularies + factors).

    Folded into the run id so any edit to reference data — even without a version
    rename — yields a new run and is caught by the reproducibility check (§8.3).
    """
    return _digest((*_RUN_REFERENCE_FILES, f"material_factors_{factor_version}.csv"))


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
    """The material vocabulary: canonical names, shorthand codes, and full-word synonyms."""

    canonical: tuple[str, ...]
    code_to_canonical: dict[str, str]
    alias_to_canonical: dict[str, str]


@functools.cache
def material_vocab() -> MaterialVocab:
    """Canonical materials in file order, the shorthand codes (``CO → cotton``), and
    the versioned synonyms (``polyamide → nylon``), each lowercased for lookup."""
    rows = _read("materials_v1.csv")
    aliases: dict[str, str] = {}
    for row in rows:
        for alias in row.get("aliases", "").split(";"):
            alias = alias.strip().lower()
            if alias:
                aliases[alias] = row["canonical"]
    return MaterialVocab(
        canonical=tuple(row["canonical"] for row in rows),
        code_to_canonical={row["code"]: row["canonical"] for row in rows if row["code"]},
        alias_to_canonical=aliases,
    )


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ReferenceWeight:
    """A representative component weight and its plausibility band (grams)."""

    ref_weight_g: float
    band_low_g: float
    band_high_g: float

    def in_band(self, grams: float) -> bool:
        """Whether a weight falls inside the plausibility band (inclusive)."""
        return self.band_low_g <= grams <= self.band_high_g


@functools.cache
def reference_weights() -> dict[str, ReferenceWeight]:
    """Representative weight + plausibility band per component (grams)."""
    return {
        row["component"]: ReferenceWeight(
            ref_weight_g=float(row["ref_weight_g"]),
            band_low_g=float(row["band_low_g"]),
            band_high_g=float(row["band_high_g"]),
        )
        for row in _read("reference_weights_v1.csv")
    }


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class MaterialFactor:
    """A material's climate-change emission factor and its citation.

    References
    ----------
    [1] Ecobalyse / ADEME Base Empreinte — https://ecobalyse.beta.gouv.fr/
    """

    factor_kgco2e_per_kg: float
    source: str
    source_version: str
    source_ref: str


@functools.cache
def material_factors(version: str = "v1") -> dict[str, MaterialFactor]:
    """Emission factor (kgCO₂e/kg) per material, from the versioned factor table.

    The table is a pinned, in-repo snapshot of Ecobalyse/ADEME material impacts so
    the data path stays offline and reproducible; it is a labeled assumption set,
    not a precise claim (brief §15). ``version`` selects ``material_factors_<v>.csv``.
    """
    return {
        row["material"]: MaterialFactor(
            factor_kgco2e_per_kg=float(row["factor_kgco2e_per_kg"]),
            source=row["source"],
            source_version=row["source_version"],
            source_ref=row["source_ref"],
        )
        for row in _read(f"material_factors_{version}.csv")
    }
