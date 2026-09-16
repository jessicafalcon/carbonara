"""Deterministic generator for the messy apparel-BOM fixture and its ground truth.

Lives outside ``carbonara/`` on purpose: it uses seeded randomness, which the
connector package forbids (carbonara-correctness §1). It builds a clean, true
table, then plants the messy conditions and fill-ladder cases the later phases
are tested against, retaining the true value of every corrupted or blanked cell.

Run ``python fixtures/generate.py`` to (re)write ``bom_v1.csv`` and
``ground_truth_v1.csv``; the same seed yields byte-identical files.
"""

from __future__ import annotations

import csv
import dataclasses
import pathlib
import random

from carbonara.contract import CANONICAL_COLUMNS

__all__ = ["SOURCE_COLUMNS", "GROUND_TRUTH_COLUMNS", "generate", "write_fixtures"]

SEED = 42

#: The raw vendor file's headers, in order. These are the connector's *input* —
#: source names that Phase 2 maps onto the canonical record, not the canonical
#: columns themselves (which the connector produces).
SOURCE_COLUMNS: tuple[str, ...] = (
    "source_row_id",
    "style_id",
    "sku",
    "component",
    "material",
    "composition",
    "net_weight",
    "supplier",
    "country",
    "order_date",
    "quantity",
    "unit_price",
)

#: Ground-truth schema: the true value of one corrupted or blanked cell, keyed by
#: source row and canonical column, labeled with the case it plants and the
#: outcome the pipeline is expected to reach for it (brief §12).
GROUND_TRUTH_COLUMNS: tuple[str, ...] = (
    "source_row_id",
    "column",
    "true_value",
    "case",
    "expected",
)


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ComponentSpec:
    """A component's believable defaults within an archetype."""

    name: str
    material: str
    composition: str
    weight_mean_g: float
    weight_cv: float
    core: bool = False


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ArchetypeSpec:
    """One garment archetype and the component lines it is built from."""

    code: str
    name: str
    components: tuple[ComponentSpec, ...]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class SupplierSpec:
    """A supplier entity, its factory country, and its messy spelling variants."""

    canonical: str
    country_raw: str
    country_iso: str
    spellings: tuple[str, ...]


# Trims shared across archetypes: small, low-variance components that make good
# dense/tight groups once they recur across many styles.
_THREAD = ComponentSpec(
    name="thread", material="polyester", composition="100% polyester", weight_mean_g=3.0, weight_cv=0.15
)
_CARE_LABEL = ComponentSpec(
    name="care label", material="polyester", composition="100% polyester", weight_mean_g=1.0, weight_cv=0.20
)
_SIZE_LABEL = ComponentSpec(
    name="size label", material="polyester", composition="100% polyester", weight_mean_g=1.0, weight_cv=0.20
)
_BRAND_LABEL = ComponentSpec(
    name="brand label", material="cotton", composition="100% cotton", weight_mean_g=2.0, weight_cv=0.20
)

ARCHETYPES: tuple[ArchetypeSpec, ...] = (
    ArchetypeSpec(
        code="TSH",
        name="t-shirt",
        components=(
            ComponentSpec(
                name="shell fabric",
                material="cotton",
                composition="100% cotton",
                weight_mean_g=150.0,
                weight_cv=0.10,
                core=True,
            ),
            ComponentSpec(
                name="rib collar",
                material="cotton",
                composition="97% cotton / 3% elastane",
                weight_mean_g=12.0,
                weight_cv=0.12,
                core=True,
            ),
            ComponentSpec(
                name="side tape", material="polyester", composition="100% polyester", weight_mean_g=4.0, weight_cv=0.15
            ),
            _THREAD,
            _CARE_LABEL,
            _SIZE_LABEL,
            _BRAND_LABEL,
        ),
    ),
    ArchetypeSpec(
        code="HOO",
        name="hoodie",
        components=(
            ComponentSpec(
                name="shell fabric",
                material="cotton",
                composition="80% cotton / 20% polyester",
                weight_mean_g=520.0,
                weight_cv=0.10,
                core=True,
            ),
            ComponentSpec(
                name="hood lining",
                material="cotton",
                composition="80% cotton / 20% polyester",
                weight_mean_g=90.0,
                weight_cv=0.12,
                core=True,
            ),
            ComponentSpec(
                name="rib cuffs",
                material="cotton",
                composition="95% cotton / 5% elastane",
                weight_mean_g=40.0,
                weight_cv=0.15,
                core=True,
            ),
            ComponentSpec(
                name="drawcord", material="polyester", composition="100% polyester", weight_mean_g=6.0, weight_cv=0.20
            ),
            ComponentSpec(
                name="metal eyelet", material="brass", composition="100% brass", weight_mean_g=2.0, weight_cv=0.25
            ),
            _THREAD,
            _CARE_LABEL,
            _SIZE_LABEL,
        ),
    ),
    ArchetypeSpec(
        code="TRO",
        name="trousers",
        components=(
            ComponentSpec(
                name="shell fabric",
                material="cotton",
                composition="98% cotton / 2% elastane",
                weight_mean_g=360.0,
                weight_cv=0.10,
                core=True,
            ),
            ComponentSpec(
                name="pocket lining",
                material="cotton",
                composition="100% cotton",
                weight_mean_g=45.0,
                weight_cv=0.12,
                core=True,
            ),
            ComponentSpec(
                name="waistband",
                material="cotton",
                composition="98% cotton / 2% elastane",
                weight_mean_g=55.0,
                weight_cv=0.12,
                core=True,
            ),
            ComponentSpec(
                name="zipper", material="polyester", composition="100% polyester", weight_mean_g=18.0, weight_cv=0.20
            ),
            ComponentSpec(name="button", material="metal", composition="100% metal", weight_mean_g=6.0, weight_cv=0.25),
            _THREAD,
            _CARE_LABEL,
            _SIZE_LABEL,
        ),
    ),
    ArchetypeSpec(
        code="DRS",
        name="dress",
        components=(
            ComponentSpec(
                name="shell fabric",
                material="viscose",
                composition="100% viscose",
                weight_mean_g=220.0,
                weight_cv=0.10,
                core=True,
            ),
            ComponentSpec(
                name="lining",
                material="polyester",
                composition="100% polyester",
                weight_mean_g=80.0,
                weight_cv=0.12,
                core=True,
            ),
            ComponentSpec(
                name="zipper", material="polyester", composition="100% polyester", weight_mean_g=14.0, weight_cv=0.20
            ),
            ComponentSpec(
                name="hook and eye", material="metal", composition="100% metal", weight_mean_g=1.5, weight_cv=0.25
            ),
            _THREAD,
            _CARE_LABEL,
            _SIZE_LABEL,
            _BRAND_LABEL,
        ),
    ),
)

SUPPLIERS: tuple[SupplierSpec, ...] = (
    SupplierSpec(
        canonical="Acme Textiles",
        country_raw="Portugal",
        country_iso="PT",
        spellings=("Acme Textiles Ltd.", "ACME TEXTILES", "Acme Textiles", "acme textiles ltd"),
    ),
    SupplierSpec(
        canonical="Golden Thread",
        country_raw="China",
        country_iso="CN",
        spellings=("Golden Thread Co.", "Golden Thread Company", "GOLDEN THREAD CO"),
    ),
    SupplierSpec(
        canonical="Bharat Mills",
        country_raw="India",
        country_iso="IN",
        spellings=("Bharat Mills", "Bharat Mills Pvt Ltd", "bharat mills"),
    ),
    SupplierSpec(
        canonical="Oceanic Fabrics",
        country_raw="Vietnam",
        country_iso="VN",
        spellings=("Oceanic Fabrics", "Oceanic Fabric", "OCEANIC FABRICS INC"),
    ),
    SupplierSpec(
        canonical="Nordic Weave",
        country_raw="Sweden",
        country_iso="SE",
        spellings=("Nordic Weave", "Nordic Weave AB", "nordic weave ab"),
    ),
)

STYLES_PER_ARCHETYPE = 12
COLORWAYS = ("BLK", "NVY", "WHT", "GRN", "RED")
SIZES = ("XS", "S", "M", "L", "XL")


def _draw_weight(rng: random.Random, spec: ComponentSpec) -> int:
    """Draw a believable positive integer gram weight for a component."""
    grams = rng.gauss(spec.weight_mean_g, spec.weight_mean_g * spec.weight_cv)
    return max(1, round(grams))


def _clean_rows(rng: random.Random) -> list[dict[str, str]]:
    """Build the clean, valid BOM: every cell well-formed, nothing yet corrupted."""
    rows: list[dict[str, str]] = []
    source_row_id = 0
    for archetype in ARCHETYPES:
        for style_index in range(1, STYLES_PER_ARCHETYPE + 1):
            style_id = f"{archetype.code}-{style_index:02d}"
            colorway = COLORWAYS[rng.randrange(len(COLORWAYS))]
            size = SIZES[rng.randrange(len(SIZES))]
            sku = f"{style_id}-{colorway}-{size}"
            supplier = SUPPLIERS[rng.randrange(len(SUPPLIERS))]
            year = 2024
            month = rng.randrange(1, 13)
            day = rng.randrange(1, 28)
            order_date = f"{year}-{month:02d}-{day:02d}"
            quantity = rng.randrange(200, 5000, 50)
            for component in _select_components(rng, archetype):
                source_row_id += 1
                rows.append(
                    {
                        "source_row_id": str(source_row_id),
                        "style_id": style_id,
                        "sku": sku,
                        "component": component.name,
                        "material": component.material,
                        "composition": component.composition,
                        "net_weight": f"{_draw_weight(rng, component)} g",
                        "supplier": supplier.canonical,
                        "country": supplier.country_raw,
                        "order_date": order_date,
                        "quantity": str(quantity),
                        "unit_price": f"{rng.uniform(0.5, 25.0):.2f}",
                    }
                )
    return rows


COMPONENTS_PER_STYLE = (5, 8)


def _select_components(rng: random.Random, archetype: ArchetypeSpec) -> list[ComponentSpec]:
    """Pick 5-8 component lines: every core component, then trims up to the target."""
    core = [c for c in archetype.components if c.core]
    optional = [c for c in archetype.components if not c.core]
    target = rng.randint(*COMPONENTS_PER_STYLE)
    extra = max(0, min(target - len(core), len(optional)))
    keep = rng.sample(optional, extra)
    # Keep trims in their declared order so a row's position is stable across runs.
    kept_optional = [c for c in optional if c in keep]
    return core + kept_optional


def generate(seed: int = SEED) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Generate the raw BOM rows and the ground-truth rows for the fixture."""
    rng = random.Random(seed)
    rows = _clean_rows(rng)
    ground_truth: list[dict[str, str]] = []
    return rows, ground_truth


def _write_csv(path: pathlib.Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    """Write rows to CSV deterministically: fixed column order, ``\\n`` line endings."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _check_ground_truth(ground_truth: list[dict[str, str]]) -> None:
    """Every ground-truth row must target a real canonical column (brief §6)."""
    canonical = set(CANONICAL_COLUMNS)
    for row in ground_truth:
        if row["column"] not in canonical:
            raise ValueError(f"ground truth targets unknown column: {row['column']!r}")


def write_fixtures(out_dir: pathlib.Path, seed: int = SEED) -> None:
    """Generate and write ``bom_v1.csv`` and ``ground_truth_v1.csv`` into ``out_dir``."""
    rows, ground_truth = generate(seed)
    _check_ground_truth(ground_truth)
    _write_csv(out_dir / "bom_v1.csv", SOURCE_COLUMNS, rows)
    _write_csv(out_dir / "ground_truth_v1.csv", GROUND_TRUTH_COLUMNS, ground_truth)


def main() -> None:
    write_fixtures(pathlib.Path(__file__).parent)


if __name__ == "__main__":
    main()
