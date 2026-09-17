"""The component-level carbon footprint: ``weight_kg × factor(material)`` (§9).

This is the project's central ``DERIVED_FORMULA`` case — the tier-1 formula
mechanism deferred from the fill ladder (§7.4). Each estimate is a derived value:
it emits a versioned :class:`RuleEvent` on the ``estimated_kgco2e`` column, so it
carries the same dual-store provenance (ledger + Bloodline) as every fill and
normalization (§8). A component whose material never resolved has no factor — it
is left unmapped and flagged, never silently costed at zero (§7.3, §15).
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable

from carbonara.contract import CanonicalRecord, QualityStatus
from carbonara.materialize import SourceRecord
from carbonara.references import factor_digest, material_factors
from carbonara.rules import AnomalyCategory, Finding, RuleEvent, Severity, SourceType

__all__ = [
    "Breakdown",
    "ComponentFootprint",
    "FactorDiff",
    "FactorDiffRow",
    "FootprintResult",
    "FootprintStatus",
    "FootprintSummary",
    "by_category",
    "by_country",
    "by_material",
    "by_product",
    "compute_footprint",
    "factor_diff",
    "summarize",
]

_RULE_ID = "footprint"
_RULE_VERSION = "v1"
_GRAMS_PER_KG = 1000
_EXACT_CONFIDENCE = 1.0


class FootprintStatus(enum.StrEnum):
    """Where a component line lands in the footprint.

    Only ``COSTED`` rows contribute to the headline totals; the others are
    reported as coverage so a filled or flagged input never hides in a sum.
    """

    COSTED = "costed"
    FLAGGED = "flagged"
    UNMAPPED = "unmapped"
    NO_WEIGHT = "no_weight"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ComponentFootprint:
    """One component line's estimate and the labels the view must display (§9)."""

    record_id: str
    style_id: str
    category: str
    component: str
    material: str | None
    factor_kgco2e_per_kg: float | None
    factor_source: str | None
    factor_source_version: str | None
    factor_version: str
    weight_g: float | None
    weight_source: str
    estimated_kgco2e: float | None
    uncertainty_kgco2e: tuple[float, float] | None
    mapping_confidence: float
    status: FootprintStatus


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class FootprintResult:
    """Per-component footprints, the derivation events, and unmapped findings."""

    components: list[ComponentFootprint]
    events: list[RuleEvent]
    findings: list[Finding]
    factor_version: str


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class FootprintSummary:
    """The catalog headline: total, uncertainty, coverage, and input share."""

    total_kgco2e: float
    uncertainty_kgco2e: tuple[float, float]
    observed_share: float
    filled_share: float
    costed_n: int
    flagged_n: int
    unmapped_n: int
    no_weight_n: int


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Breakdown:
    """A footprint total for one grouping key (material, category, country, …)."""

    key: str
    total_kgco2e: float
    uncertainty_kgco2e: tuple[float, float]
    costed_n: int
    observed_share: float
    filled_share: float


def _category(style_id: str) -> str:
    return style_id.split("-")[0]


def _filled_weight_events(fill_events: list[RuleEvent]) -> dict[str, RuleEvent]:
    """Index weight-fill events by record id, to label observed vs. filled."""
    tiers = {SourceType.GROUPED_MEDIAN, SourceType.REFERENCE_CONSTANT, SourceType.DERIVED_FORMULA}
    return {e.record_id: e for e in fill_events if e.column == "component_weight_g" and e.source_type in tiers}


def compute_footprint(
    records: list[SourceRecord], fill_events: list[RuleEvent], *, factor_version: str = "v1"
) -> FootprintResult:
    """Cost each component by ``weight_kg × factor(material)``, with provenance.

    ``fill_events`` are the fill pass's events, used to label whether the weight
    behind an estimate was observed or filled (and to propagate the filled range).
    A missing weight yields ``NO_WEIGHT``; an unresolved material yields
    ``UNMAPPED`` with a mapping finding; a flagged implausible weight is still
    derived but excluded from the totals. Only ``COSTED`` rows carry a
    ``DERIVED_FORMULA`` event.

    >>> from carbonara.contract import CanonicalRecord
    >>> rec = CanonicalRecord(record_id="r0001", source_row_id="1", style_id="TSH-1", sku="S",
    ...     component="shell fabric", material_raw="cotton", material_normalized="cotton",
    ...     component_weight_g=200.0, supplier_raw="Acme")
    >>> result = compute_footprint([SourceRecord(record=rec, raw={})], [])
    >>> round(result.components[0].estimated_kgco2e, 3)  # 0.2 kg × 3.4151
    0.683
    >>> result.components[0].status
    <FootprintStatus.COSTED: 'costed'>
    """
    factors = material_factors(factor_version)
    factor_hash = factor_digest(factor_version)
    filled = _filled_weight_events(fill_events)

    components: list[ComponentFootprint] = []
    events: list[RuleEvent] = []
    findings: list[Finding] = []

    for source in records:
        record = source.record
        weight = record.component_weight_g
        material = record.material_normalized

        if weight is None:
            components.append(_uncosted(record, factor_version, weight_g=None, status=FootprintStatus.NO_WEIGHT))
            continue

        factor = factors.get(material) if material is not None else None
        if factor is None:
            components.append(_uncosted(record, factor_version, weight_g=weight, status=FootprintStatus.UNMAPPED))
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="estimated_kgco2e",
                    category=AnomalyCategory.MAPPING,
                    severity=Severity.MEDIUM,
                    message=f"material {material!r} has no emission factor — component not costed",
                    evidence={"material_raw": record.material_raw},
                )
            )
            continue

        estimate = weight / _GRAMS_PER_KG * factor.factor_kgco2e_per_kg
        fill_event = filled.get(record.record_id)
        weight_source = "filled" if fill_event is not None else "observed"
        uncertainty = _propagate(fill_event, factor.factor_kgco2e_per_kg)
        flagged = record.quality_status is QualityStatus.FLAGGED
        status = FootprintStatus.FLAGGED if flagged else FootprintStatus.COSTED

        components.append(
            ComponentFootprint(
                record_id=record.record_id,
                style_id=record.style_id,
                category=_category(record.style_id),
                component=record.component,
                factor_version=factor_version,
                material=material,
                factor_kgco2e_per_kg=factor.factor_kgco2e_per_kg,
                factor_source=factor.source,
                factor_source_version=factor.source_version,
                weight_g=weight,
                weight_source=weight_source,
                estimated_kgco2e=estimate,
                uncertainty_kgco2e=uncertainty,
                mapping_confidence=_EXACT_CONFIDENCE,
                status=status,
            )
        )
        events.append(
            RuleEvent.create(
                record_id=record.record_id,
                column="estimated_kgco2e",
                rule_id=_RULE_ID,
                rule_version=_RULE_VERSION,
                source_type=SourceType.DERIVED_FORMULA,
                value_before=None,
                value_after=str(estimate),
                method_params={
                    "material": material,
                    "factor_kgco2e_per_kg": factor.factor_kgco2e_per_kg,
                    "factor_source": factor.source,
                    "factor_source_version": factor.source_version,
                    "factor_table_version": factor_version,
                    "factor_content_hash": factor_hash,
                    "weight_g": weight,
                    "weight_source": weight_source,
                    "mapping_confidence": _EXACT_CONFIDENCE,
                    "flagged": flagged,
                },
                uncertainty_range=uncertainty,
            )
        )

    return FootprintResult(components=components, events=events, findings=findings, factor_version=factor_version)


def _uncosted(
    record: CanonicalRecord, factor_version: str, *, weight_g: float | None, status: FootprintStatus
) -> ComponentFootprint:
    """A component row that carries no estimate (missing weight or unmapped material)."""
    return ComponentFootprint(
        record_id=record.record_id,
        style_id=record.style_id,
        category=_category(record.style_id),
        component=record.component,
        factor_version=factor_version,
        material=record.material_normalized,
        factor_kgco2e_per_kg=None,
        factor_source=None,
        factor_source_version=None,
        weight_g=weight_g,
        weight_source="missing" if weight_g is None else "observed",
        estimated_kgco2e=None,
        uncertainty_kgco2e=None,
        mapping_confidence=0.0,
        status=status,
    )


def _propagate(fill_event: RuleEvent | None, factor: float) -> tuple[float, float] | None:
    """Propagate a filled weight's gram range through the factor, else no range.

    An observed weight is a point estimate (no range); only a filled weight
    carries an uncertainty range to propagate (§7.5).
    """
    if fill_event is None or fill_event.uncertainty_range is None:
        return None
    low_g, high_g = fill_event.uncertainty_range
    return (low_g / _GRAMS_PER_KG * factor, high_g / _GRAMS_PER_KG * factor)


def _costed(result: FootprintResult) -> list[ComponentFootprint]:
    return [c for c in result.components if c.status is FootprintStatus.COSTED]


def _estimates(components: list[ComponentFootprint]) -> list[float]:
    """The present estimates, narrowing away the ``None`` of an uncosted row."""
    return [c.estimated_kgco2e for c in components if c.estimated_kgco2e is not None]


def _range(components: list[ComponentFootprint]) -> tuple[float, float]:
    """Sum each row's bounds; an observed point contributes as [est, est]."""
    low = high = 0.0
    for c in components:
        est = c.estimated_kgco2e
        if est is None:
            continue
        band = c.uncertainty_kgco2e or (est, est)
        low += band[0]
        high += band[1]
    return (low, high)


def _shares(components: list[ComponentFootprint], total: float) -> tuple[float, float]:
    """Fraction of the total kgCO₂e resting on observed vs. filled weights."""
    if total == 0:
        return (0.0, 0.0)
    observed = sum(_estimates([c for c in components if c.weight_source == "observed"]))
    return (observed / total, 1 - observed / total)


def summarize(result: FootprintResult) -> FootprintSummary:
    """The catalog headline over costed rows, with coverage and input share."""
    costed = _costed(result)
    total = sum(_estimates(costed))
    observed_share, filled_share = _shares(costed, total)
    by_status = {s: 0 for s in FootprintStatus}
    for c in result.components:
        by_status[c.status] += 1
    return FootprintSummary(
        total_kgco2e=total,
        uncertainty_kgco2e=_range(costed),
        observed_share=observed_share,
        filled_share=filled_share,
        costed_n=by_status[FootprintStatus.COSTED],
        flagged_n=by_status[FootprintStatus.FLAGGED],
        unmapped_n=by_status[FootprintStatus.UNMAPPED],
        no_weight_n=by_status[FootprintStatus.NO_WEIGHT],
    )


def _aggregate(components: list[ComponentFootprint], key_fn: Callable[[ComponentFootprint], str]) -> list[Breakdown]:
    """Group costed rows by a key, sorted by total descending then key."""
    groups: dict[str, list[ComponentFootprint]] = {}
    for c in components:
        if c.status is FootprintStatus.COSTED:
            groups.setdefault(key_fn(c), []).append(c)
    breakdowns = []
    for name, rows in groups.items():
        total = sum(_estimates(rows))
        observed_share, filled_share = _shares(rows, total)
        breakdowns.append(
            Breakdown(
                key=name,
                total_kgco2e=total,
                uncertainty_kgco2e=_range(rows),
                costed_n=len(rows),
                observed_share=observed_share,
                filled_share=filled_share,
            )
        )
    return sorted(breakdowns, key=lambda b: (-b.total_kgco2e, b.key))


def by_material(result: FootprintResult) -> list[Breakdown]:
    """Footprint by material, largest first."""
    return _aggregate(result.components, lambda c: c.material or "unmapped")


def by_category(result: FootprintResult) -> list[Breakdown]:
    """Footprint by garment archetype (style prefix), largest first."""
    return _aggregate(result.components, lambda c: c.category)


def by_product(result: FootprintResult) -> list[Breakdown]:
    """Footprint by product (style id), largest first."""
    return _aggregate(result.components, lambda c: c.style_id)


def by_country(records: list[SourceRecord], result: FootprintResult) -> list[Breakdown]:
    """Footprint by factory country ISO, largest first.

    Country lives on the record, not the footprint row, so it is joined here by
    record id rather than carried on every :class:`ComponentFootprint`.
    """
    iso = {s.record.record_id: (s.record.factory_country_iso or "unknown") for s in records}
    return _aggregate(result.components, lambda c: iso.get(c.record_id, "unknown"))


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class FactorDiffRow:
    """One material's footprint under two factor versions, and the delta."""

    material: str
    factor_from: float
    factor_to: float
    total_from: float
    total_to: float
    delta_kgco2e: float


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class FactorDiff:
    """A footprint recomputed across a factor revision, catalog- and material-level.

    The revision recomputes the estimate; it does not rewrite history — the
    two runs live under distinct ``run_id``s in the append-only ledger (§8.2).
    """

    from_version: str
    to_version: str
    total_from: float
    total_to: float
    delta_kgco2e: float
    rows: list[FactorDiffRow]


def factor_diff(
    records: list[SourceRecord], fill_events: list[RuleEvent], *, from_version: str, to_version: str
) -> FactorDiff:
    """Recompute the footprint under two factor versions and diff by material.

    Rows are only those materials whose factor changed, largest absolute delta
    first. Weights are held fixed — this isolates the factor (intensity) effect.
    """
    before = compute_footprint(records, fill_events, factor_version=from_version)
    after = compute_footprint(records, fill_events, factor_version=to_version)
    factors_from = material_factors(from_version)
    factors_to = material_factors(to_version)
    totals_from = {b.key: b.total_kgco2e for b in by_material(before)}
    totals_to = {b.key: b.total_kgco2e for b in by_material(after)}

    rows = []
    for material in sorted(totals_from.keys() | totals_to.keys()):
        f_from = factors_from[material].factor_kgco2e_per_kg
        f_to = factors_to[material].factor_kgco2e_per_kg
        if f_from == f_to:
            continue
        t_from = totals_from.get(material, 0.0)
        t_to = totals_to.get(material, 0.0)
        rows.append(
            FactorDiffRow(
                material=material,
                factor_from=f_from,
                factor_to=f_to,
                total_from=t_from,
                total_to=t_to,
                delta_kgco2e=t_to - t_from,
            )
        )
    rows.sort(key=lambda r: (-abs(r.delta_kgco2e), r.material))
    total_from = summarize(before).total_kgco2e
    total_to = summarize(after).total_kgco2e
    return FactorDiff(
        from_version=from_version,
        to_version=to_version,
        total_from=total_from,
        total_to=total_to,
        delta_kgco2e=total_to - total_from,
        rows=rows,
    )
