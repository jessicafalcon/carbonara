"""The weight fill ladder: grouped median → reference constant → leave null (§7.4).

The brief's five tiers are realized across the pipeline, first-match-wins per
missing cell — a missing weight enters at tier 3 because tiers 1–2 have no
applicable input for this gap type, by the fixture's design, not by omission:

1. **Formula** — no weight gap has formula inputs (the source carries no
   garment-total weight), so it is not reached here. The ``DERIVED_FORMULA``
   mechanism is exercised by the footprint (``weight × factor``) in Phase 5.
2. **Reference-resolve** — realized at normalization (Phase 3): country→ISO,
   material vocabulary, supplier fuzzy-match. A continuous weight is not
   reference-resolvable.
3. **Grouped median** with support / dispersion / plausibility guards (below).
4. **Reference constant**, marked as an assumption.
5. **Leave null**, ``action_required``.
"""

from __future__ import annotations

import dataclasses
import statistics
from collections.abc import Callable

from carbonara.contract import QualityStatus
from carbonara.materialize import SourceRecord
from carbonara.references import reference_weights
from carbonara.rules import AnomalyCategory, Finding, RuleEvent, Severity, SourceType

__all__ = ["FillResult", "fill_weights"]

_RULESET_VERSION = "v1"
#: Grouped-median guards (brief §7.6), versioned config — no magic numbers.
_SUPPORT_N = 5
_DISPERSION_CUTOFF = 0.30
_BAND_REF = "reference_weights_v1"

_Key = tuple[str, ...]
_KeyFn = Callable[[SourceRecord], _Key]


def _category(record: SourceRecord) -> str:
    return record.record.style_id.split("-")[0]


def _material(record: SourceRecord) -> str:
    return record.record.material_normalized or record.record.material_raw.lower()


#: Back-off levels, finest first (brief §7.6). Stops at category — never a global median.
_BACKOFF: tuple[tuple[str, _KeyFn], ...] = (
    ("material×component×category", lambda r: (_material(r), r.record.component, _category(r))),
    ("component×category", lambda r: (r.record.component, _category(r))),
    ("category", lambda r: (_category(r),)),
)


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class FillResult:
    """Records with weights filled, the fill events, and any findings raised."""

    records: list[SourceRecord]
    events: list[RuleEvent]
    findings: list[Finding]


def _pools(records: list[SourceRecord]) -> list[tuple[str, _KeyFn, dict[_Key, list[float]]]]:
    """Index observed positive weights by each back-off level's group key.

    Implausible observations are kept in the pool: the median is robust to a lone
    outlier, dropping them would push a tight group below the support floor, and
    the plausibility guard already protects the *result*, not the inputs.
    """
    observed = [r for r in records if r.record.component_weight_g and r.record.component_weight_g > 0]
    pools: list[tuple[str, _KeyFn, dict[_Key, list[float]]]] = []
    for name, key_fn in _BACKOFF:
        grouped: dict[_Key, list[float]] = {}
        for record in observed:
            weight = record.record.component_weight_g
            assert weight is not None  # narrowed by the `observed` filter
            grouped.setdefault(key_fn(record), []).append(weight)
        pools.append((name, key_fn, grouped))
    return pools


def _median_fill(
    record: SourceRecord, pools: list[tuple[str, _KeyFn, dict[_Key, list[float]]]]
) -> tuple[RuleEvent, float] | None:
    """Fill from the finest group clearing support, dispersion, and plausibility."""
    ref = reference_weights().get(record.record.component)
    for name, key_fn, grouped in pools:
        values = grouped.get(key_fn(record), [])
        if len(values) < _SUPPORT_N:
            continue
        median = statistics.median(values)
        mad = statistics.median([abs(v - median) for v in values])
        if median == 0 or mad / median > _DISPERSION_CUTOFF:
            continue
        if ref is not None and not ref.in_band(median):
            continue  # rejected → fall through to the reference constant
        event = RuleEvent.create(
            record_id=record.record.record_id,
            column="component_weight_g",
            rule_id="weight_median",
            rule_version=_RULESET_VERSION,
            source_type=SourceType.GROUPED_MEDIAN,
            value_before="",
            value_after=str(median),
            method_params={
                "group": name,
                "n": len(values),
                "dispersion": round(mad / median, 4),
                "band_ref": _BAND_REF,
            },
            uncertainty_range=(median - mad, median + mad),
        )
        return event, median
    return None


def _constant_fill(record: SourceRecord) -> tuple[RuleEvent, float] | None:
    """Fill from the component's reference constant, marked as an assumption."""
    ref = reference_weights().get(record.record.component)
    if ref is None:
        return None
    event = RuleEvent.create(
        record_id=record.record.record_id,
        column="component_weight_g",
        rule_id="weight_constant",
        rule_version=_RULESET_VERSION,
        source_type=SourceType.REFERENCE_CONSTANT,
        value_before="",
        value_after=str(ref.ref_weight_g),
        method_params={"assumption": True, "component": record.record.component, "band_ref": _BAND_REF},
        uncertainty_range=(ref.band_low_g, ref.band_high_g),
    )
    return event, ref.ref_weight_g


def fill_weights(records: list[SourceRecord]) -> FillResult:
    """Fill every missing ``component_weight_g`` by the ladder; flag implausible observed.

    First match wins: grouped median (support/dispersion/plausibility) → reference
    constant → leave null (``action_required``). An observed weight outside its
    component band is flagged (``FLAGGED``), never silently changed.
    """
    pools = _pools(records)
    out: list[SourceRecord] = []
    events: list[RuleEvent] = []
    findings: list[Finding] = []

    for source in records:
        record = source.record
        weight = record.component_weight_g

        if weight is None:
            # tiers 3 → 4 → 5, first match wins (tiers 1–2 unreachable here; see docstring)
            filled = _median_fill(source, pools) or _constant_fill(source)
            if filled is None:
                out.append(
                    dataclasses.replace(
                        source, record=dataclasses.replace(record, quality_status=QualityStatus.ACTION_REQUIRED)
                    )
                )
                continue
            event, value = filled
            events.append(event)
            out.append(dataclasses.replace(source, record=dataclasses.replace(record, component_weight_g=value)))
            continue

        ref = reference_weights().get(record.component)
        if weight > 0 and ref is not None and not ref.in_band(weight):
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="component_weight_g",
                    category=AnomalyCategory.PLAUSIBILITY,
                    severity=Severity.HIGH,
                    message=f"observed weight {weight} outside band [{ref.band_low_g}, {ref.band_high_g}]",
                    evidence={"value": weight},
                )
            )
            out.append(
                dataclasses.replace(source, record=dataclasses.replace(record, quality_status=QualityStatus.FLAGGED))
            )
            continue

        out.append(source)

    return FillResult(records=out, events=events, findings=findings)
