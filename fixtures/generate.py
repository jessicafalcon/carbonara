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
from collections.abc import Callable

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


# One header is renamed from the connector's expected source name, so a first
# import trips the schema-drift gate (brief §12) rather than mapping silently.
RENAMED_HEADERS: dict[str, str] = {"supplier": "vendor"}


def _record(
    ground_truth: list[dict[str, str]],
    *,
    source_row_id: str,
    column: str,
    true_value: str,
    case: str,
    expected: str,
) -> None:
    """Append one ground-truth row: the true value of a corrupted/blanked cell."""
    ground_truth.append(
        {
            "source_row_id": source_row_id,
            "column": column,
            "true_value": true_value,
            "case": case,
            "expected": expected,
        }
    )


def _next_id(rows: list[dict[str, str]]) -> int:
    """The next free source_row_id (ids are the 1-based file row order)."""
    return max(int(r["source_row_id"]) for r in rows) + 1


def _parse_grams(net_weight: str) -> int:
    """Read the integer grams out of a clean ``'<n> g'`` cell."""
    return int(net_weight.split()[0])


def _pick(
    rng: random.Random,
    rows: list[dict[str, str]],
    used: set[str],
    predicate: Callable[[dict[str, str]], bool],
    n: int,
) -> list[dict[str, str]]:
    """Deterministically choose up to ``n`` unused rows matching ``predicate``."""
    candidates = [r for r in rows if r["source_row_id"] not in used and predicate(r)]
    chosen = rng.sample(candidates, min(n, len(candidates)))
    for row in chosen:
        used.add(row["source_row_id"])
    return chosen


def _plant_renamed_header(ground_truth: list[dict[str, str]]) -> None:
    """A vendor renamed one column; source_row_id 0 marks a file/header-level case."""
    _record(
        ground_truth,
        source_row_id="0",
        column="supplier_raw",
        true_value="supplier",
        case="renamed_header",
        expected="schema-drift warning, review required",
    )


def _plant_file_level_cases(ground_truth: list[dict[str, str]]) -> None:
    """Record the §12 behaviors that are file/pipeline scope, not a single cell.

    Both are exercised by later phases against this same file — re-importing its
    bytes (Phase 2) and revising a reference factor (Phase 5) — but their
    expected outcomes are registered here so the §12 table is fully covered.
    """
    _record(
        ground_truth,
        source_row_id="0",
        column="",
        true_value="",
        case="duplicate_file_upload",
        expected="idempotent rerun, no duplicate rows",
    )
    _record(
        ground_truth,
        source_row_id="0",
        column="",
        true_value="",
        case="factor_table_revision",
        expected="recalculated metrics + factor-version diff",
    )


def _plant_supplier_variants(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Swap a few of each supplier's rows to a messy spelling variant, keeping truth."""
    for supplier in SUPPLIERS:
        for spelling in supplier.spellings:
            if spelling == supplier.canonical:
                continue
            for row in _pick(rng, rows, used, lambda r, s=supplier: r["supplier"] == s.canonical, 2):
                row["supplier"] = spelling
                _record(
                    ground_truth,
                    source_row_id=row["source_row_id"],
                    column="supplier_normalized",
                    true_value=supplier.canonical,
                    case="supplier_variant",
                    expected="fuzzy match to canonical supplier above threshold",
                )


def _plant_material_typo(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """`Organic cottn`: a material misspelling that must be proposed, not auto-fixed."""
    for row in _pick(rng, rows, used, lambda r: r["material"] == "cotton", 3):
        row["material"] = "Organic cottn"
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="material_normalized",
            true_value="organic cotton",
            case="material_typo",
            expected="proposed alias, not silent correction",
        )


def _plant_composition_shorthand(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """`70/30 CO/PL`: shorthand composition to parse and check sums to 100%."""
    for row in _pick(rng, rows, used, lambda r: r["component"] == "shell fabric", 3):
        row["composition"] = "70/30 CO/PL"
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="composition",
            true_value="70% cotton / 30% polyester",
            case="composition_shorthand",
            expected="composition parsed, sums to 100%",
        )


def _plant_mixed_units(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Weights given in kg on heavy components: normalize to grams, preserve the raw."""
    for row in _pick(rng, rows, used, lambda r: _parse_grams(r["net_weight"]) >= 200, 4):
        grams = _parse_grams(row["net_weight"])
        row["net_weight"] = f"{grams / 1000:.2f} kg"
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="component_weight_g",
            true_value=str(grams),
            case="mixed_units_kg",
            expected="normalized value + preserved raw value/unit",
        )


def _plant_zero_weight(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Zero weight beside a positive quantity/value: a high-severity anomaly, not a fill."""
    for row in _pick(rng, rows, used, lambda r: _parse_grams(r["net_weight"]) >= 50, 1):
        grams = _parse_grams(row["net_weight"])
        row["net_weight"] = "0 g"
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="component_weight_g",
            true_value=str(grams),
            case="zero_weight_positive_value",
            expected="high-severity anomaly",
        )


def _plant_malformed_dates(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Unparseable order dates: a validity anomaly; the true date is retained."""
    malformed = ("2024-13-07", "2024/02/31")
    for row, bad in zip(_pick(rng, rows, used, lambda r: True, len(malformed)), malformed, strict=True):
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="order_date",
            true_value=row["order_date"],
            case="malformed_date",
            expected="validity anomaly (invalid date)",
        )
        row["order_date"] = bad


def _plant_extreme_price(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """An implausible unit price: a distribution anomaly flagged for review."""
    for row in _pick(rng, rows, used, lambda r: True, 1):
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="unit_price",
            true_value=row["unit_price"],
            case="extreme_price",
            expected="distribution anomaly (extreme price)",
        )
        row["unit_price"] = "9999.00"


def _plant_duplicate_key(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Re-emit a row under a new file id but the same business key: must not double-count."""
    (original,) = _pick(rng, rows, used, lambda r: True, 1)
    duplicate = dict(original)
    duplicate["source_row_id"] = str(_next_id(rows))
    rows.append(duplicate)
    used.add(duplicate["source_row_id"])
    _record(
        ground_truth,
        source_row_id=duplicate["source_row_id"],
        column="record_id",
        true_value=original["source_row_id"],
        case="duplicate_key",
        expected="finding, no double counting",
    )


# Fill-ladder planted groups. Support N=5 is the connector's floor (brief §7.6):
# the high-spread group has n>5 but wide weights (fails dispersion), the sparse
# group has n<5 (fails support). Both then fall through to the reference constant.
MISSINGNESS_RATE = 0.35
_HIGH_SPREAD_WEIGHTS = (40, 9, 66, 16, 92, 27)
_SPARSE_WEIGHTS = (31, 34)


def _distinct_style_donors(rows: list[dict[str, str]], code: str, n: int) -> list[dict[str, str]]:
    """Return one row per distinct style of an archetype, to lend style-level identity."""
    donors: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not row["style_id"].startswith(f"{code}-") or row["style_id"] in seen:
            continue
        seen.add(row["style_id"])
        donors.append(row)
        if len(donors) == n:
            break
    return donors


def _clone_line(
    rng: random.Random,
    donor: dict[str, str],
    *,
    source_row_id: int,
    component: str,
    material: str,
    composition: str,
    net_weight: str,
) -> dict[str, str]:
    """Add a planted component line to an existing style, borrowing its identity."""
    line = dict(donor)
    line.update(
        source_row_id=str(source_row_id),
        component=component,
        material=material,
        composition=composition,
        net_weight=net_weight,
        unit_price=f"{rng.uniform(0.5, 25.0):.2f}",
    )
    return line


def _plant_high_spread_group(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """A group with support but wide weights: the median fails the dispersion guard."""
    donors = _distinct_style_donors(rows, "TRO", len(_HIGH_SPREAD_WEIGHTS) + 1)
    for donor, grams in zip(donors[:-1], _HIGH_SPREAD_WEIGHTS, strict=True):
        line = _clone_line(
            rng,
            donor,
            source_row_id=_next_id(rows),
            component="webbing strap",
            material="nylon",
            composition="100% nylon",
            net_weight=f"{grams} g",
        )
        rows.append(line)
        used.add(line["source_row_id"])
    blank = _clone_line(
        rng,
        donors[-1],
        source_row_id=_next_id(rows),
        component="webbing strap",
        material="nylon",
        composition="100% nylon",
        net_weight="",
    )
    rows.append(blank)
    used.add(blank["source_row_id"])
    _record(
        ground_truth,
        source_row_id=blank["source_row_id"],
        column="component_weight_g",
        true_value="45",
        case="blank_weight_high_spread",
        expected="fails dispersion -> reference constant",
    )


def _plant_sparse_group(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """A group with too few observations: the median fails the support guard."""
    donors = _distinct_style_donors(rows, "DRS", len(_SPARSE_WEIGHTS) + 1)
    for donor, grams in zip(donors[:-1], _SPARSE_WEIGHTS, strict=True):
        line = _clone_line(
            rng,
            donor,
            source_row_id=_next_id(rows),
            component="sequin panel",
            material="polyester",
            composition="100% polyester",
            net_weight=f"{grams} g",
        )
        rows.append(line)
        used.add(line["source_row_id"])
    blank = _clone_line(
        rng,
        donors[-1],
        source_row_id=_next_id(rows),
        component="sequin panel",
        material="polyester",
        composition="100% polyester",
        net_weight="",
    )
    rows.append(blank)
    used.add(blank["source_row_id"])
    _record(
        ground_truth,
        source_row_id=blank["source_row_id"],
        column="component_weight_g",
        true_value="32",
        case="blank_weight_sparse",
        expected="fails support -> reference constant",
    )


def _plant_implausible_weight(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """An observed weight far outside the reference band: flagged, not accepted."""
    predicate = lambda r: (  # noqa: E731 - a local row predicate reads clearest inline
        r["style_id"].startswith("TSH-") and r["component"] == "shell fabric" and r["material"] == "cotton"
    )
    for row in _pick(rng, rows, used, predicate, 1):
        grams = _parse_grams(row["net_weight"])
        row["net_weight"] = "5000 g"
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="component_weight_g",
            true_value=str(grams),
            case="implausible_weight",
            expected="trips plausibility band -> rejected/flagged",
        )


def _plant_dense_tight_blanks(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Blank a few weights in a dense, tight group: they fill cleanly at the median tier."""
    predicate = lambda r: (  # noqa: E731 - a local row predicate reads clearest inline
        r["style_id"].startswith("TSH-")
        and r["component"] == "shell fabric"
        and r["material"] == "cotton"
        and r["net_weight"].endswith(" g")
    )
    for row in _pick(rng, rows, used, predicate, 3):
        grams = _parse_grams(row["net_weight"])
        row["net_weight"] = ""
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="component_weight_g",
            true_value=str(grams),
            case="blank_weight_dense_tight",
            expected="GROUPED_MEDIAN fill",
        )


def _plant_missingness_band(
    rng: random.Random, rows: list[dict[str, str]], ground_truth: list[dict[str, str]], used: set[str]
) -> None:
    """Blank ~35% of the remaining gram weights: enough gaps to make filling matter."""
    eligible = [r for r in rows if r["source_row_id"] not in used and r["net_weight"].endswith(" g")]
    count = round(MISSINGNESS_RATE * len(eligible))
    for row in rng.sample(eligible, count):
        grams = _parse_grams(row["net_weight"])
        row["net_weight"] = ""
        used.add(row["source_row_id"])
        _record(
            ground_truth,
            source_row_id=row["source_row_id"],
            column="component_weight_g",
            true_value=str(grams),
            case="blank_weight",
            expected="grouped-median fill where the group clears guards, else reference constant",
        )


def generate(seed: int = SEED) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Generate the raw BOM rows and the ground-truth rows for the fixture."""
    rng = random.Random(seed)
    rows = _clean_rows(rng)
    ground_truth: list[dict[str, str]] = []
    used: set[str] = set()
    _plant_renamed_header(ground_truth)
    _plant_supplier_variants(rng, rows, ground_truth, used)
    _plant_material_typo(rng, rows, ground_truth, used)
    _plant_composition_shorthand(rng, rows, ground_truth, used)
    _plant_mixed_units(rng, rows, ground_truth, used)
    _plant_zero_weight(rng, rows, ground_truth, used)
    _plant_malformed_dates(rng, rows, ground_truth, used)
    _plant_extreme_price(rng, rows, ground_truth, used)
    _plant_duplicate_key(rng, rows, ground_truth, used)
    _plant_high_spread_group(rng, rows, ground_truth, used)
    _plant_sparse_group(rng, rows, ground_truth, used)
    _plant_implausible_weight(rng, rows, ground_truth, used)
    _plant_dense_tight_blanks(rng, rows, ground_truth, used)
    _plant_missingness_band(rng, rows, ground_truth, used)
    _plant_file_level_cases(ground_truth)
    return rows, ground_truth


def _write_csv(path: pathlib.Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    """Write rows to CSV deterministically: fixed column order, ``\\n`` line endings."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_bom(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    """Write the BOM with the planted header rename applied to the emitted header row."""
    headers = [RENAMED_HEADERS.get(column, column) for column in SOURCE_COLUMNS]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows([row[column] for column in SOURCE_COLUMNS] for row in rows)


def _check_ground_truth(rows: list[dict[str, str]], ground_truth: list[dict[str, str]]) -> None:
    """Ground truth must be well-formed and retain every blanked weight cell.

    Row-level entries target a real canonical column (brief §6); file-level
    entries (source_row_id 0) carry no column. Every blanked ``component_weight_g``
    cell must have its true value retained, so fill accuracy stays measurable.
    """
    canonical = set(CANONICAL_COLUMNS)
    for row in ground_truth:
        if row["source_row_id"] == "0":
            continue
        if row["column"] not in canonical:
            raise ValueError(f"ground truth targets unknown column: {row['column']!r}")

    retained_weights = {row["source_row_id"] for row in ground_truth if row["column"] == "component_weight_g"}
    for row in rows:
        if row["net_weight"] == "" and row["source_row_id"] not in retained_weights:
            raise ValueError(f"blanked weight has no retained truth: row {row['source_row_id']}")


def write_fixtures(out_dir: pathlib.Path, seed: int = SEED) -> None:
    """Generate and write ``bom_v1.csv`` and ``ground_truth_v1.csv`` into ``out_dir``."""
    rows, ground_truth = generate(seed)
    _check_ground_truth(rows, ground_truth)
    _write_bom(out_dir / "bom_v1.csv", rows)
    _write_csv(out_dir / "ground_truth_v1.csv", GROUND_TRUTH_COLUMNS, ground_truth)


def main() -> None:
    write_fixtures(pathlib.Path(__file__).parent)


if __name__ == "__main__":
    main()
