"""Deterministic normalization rules: dates, weights→grams, composition, references."""

from __future__ import annotations

import dataclasses
import datetime
import difflib
import re

from carbonara.materialize import SourceRecord
from carbonara.references import country_iso, material_vocab, supplier_names
from carbonara.rules import AnomalyCategory, Finding, RuleEvent, Severity, SourceType

__all__ = [
    "NormalizeResult",
    "format_composition",
    "normalize_records",
    "parse_composition",
    "parse_date",
    "parse_weight",
    "resolve_country",
    "resolve_material",
    "resolve_supplier",
]

_WEIGHT = re.compile(r"([\d.]+)\s*(kg|g)", re.IGNORECASE)
_SHORTHAND = re.compile(r"(\d+)\s*/\s*(\d+)\s+([A-Za-z]{2,})\s*/\s*([A-Za-z]{2,})")
_PERCENT_PART = re.compile(r"(\d+)\s*%\s*(.+)")
_GRAMS_PER_KG = 1000

#: Fuzzy-match cutoffs, calibrated to the fixture: the widest legitimate supplier
#: variant ("Bharat Mills Pvt Ltd") matches its canonical at 0.75, and the one
#: material typo ("Organic cottn" → "organic cotton") at 0.96.
_SUPPLIER_THRESHOLD = 0.75
_MATERIAL_PROPOSAL_THRESHOLD = 0.85


def parse_date(raw: str) -> datetime.date | None:
    """Parse an ISO date, or ``None`` for a blank or malformed value.

    >>> parse_date("2024-01-08")
    datetime.date(2024, 1, 8)
    >>> parse_date("2024-13-07") is None  # month 13
    True
    >>> parse_date("2024/02/31") is None  # slashes, invalid day
    True
    """
    try:
        return datetime.date.fromisoformat(raw.strip())
    except ValueError:
        return None


def parse_weight(raw: str) -> float | None:
    """Parse a weight to grams, or ``None`` if there is no number+unit to parse.

    The raw value and unit are preserved by the caller (the source row); this
    returns only the normalized grams.

    >>> parse_weight("200 g")
    200.0
    >>> parse_weight("0.49 kg")  # honest conversion of the given value
    490.0
    >>> parse_weight("0 g")
    0.0
    >>> parse_weight("") is None
    True
    """
    match = _WEIGHT.fullmatch(raw.strip())
    if match is None:
        return None
    value = float(match.group(1))
    return value * _GRAMS_PER_KG if match.group(2).lower() == "kg" else value


def _resolve_material(token: str) -> str:
    """Expand a shorthand code (``CO``) to its canonical material, else lowercase."""
    vocab = material_vocab()
    return vocab.code_to_canonical.get(token.upper(), token.strip().lower())


def parse_composition(raw: str) -> list[tuple[float, str]] | None:
    """Parse a composition to ordered ``(fraction, material)`` pairs, or ``None``.

    Handles the ``70/30 CO/PL`` shorthand and the ``80% cotton / 20% polyester``
    percent form; codes are expanded via the material vocabulary. The fractions
    are returned as given — checking that they sum to 1.0 is a validation step,
    not this parser's job.

    >>> parse_composition("70/30 CO/PL")
    [(0.7, 'cotton'), (0.3, 'polyester')]
    >>> parse_composition("100% cotton")
    [(1.0, 'cotton')]
    >>> parse_composition("80% cotton / 20% polyester")
    [(0.8, 'cotton'), (0.2, 'polyester')]
    """
    text = raw.strip()
    shorthand = _SHORTHAND.fullmatch(text)
    if shorthand is not None:
        p1, p2, c1, c2 = shorthand.groups()
        return [(int(p1) / 100, _resolve_material(c1)), (int(p2) / 100, _resolve_material(c2))]

    pairs: list[tuple[float, str]] = []
    for part in text.split("/"):
        match = _PERCENT_PART.fullmatch(part.strip())
        if match is None:
            return None
        pairs.append((int(match.group(1)) / 100, _resolve_material(match.group(2))))
    return pairs or None


def format_composition(pairs: list[tuple[float, str]]) -> str:
    """Render parsed pairs as the canonical composition string.

    >>> format_composition([(0.7, "cotton"), (0.3, "polyester")])
    '70% cotton / 30% polyester'
    """
    return " / ".join(f"{round(fraction * 100)}% {material}" for fraction, material in pairs)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def resolve_country(raw: str) -> str | None:
    """Resolve a country name to its ISO-3166 alpha-2 code, or ``None``.

    >>> resolve_country("Portugal")
    'PT'
    >>> resolve_country("Atlantis") is None
    True
    """
    return country_iso().get(raw.strip().lower())


def resolve_supplier(raw: str) -> tuple[str, float] | None:
    """Fuzzy-match a supplier spelling to a canonical name above the threshold.

    Returns ``(canonical, ratio)`` for the best match that clears the cutoff.

    >>> resolve_supplier("ACME TEXTILES")
    ('Acme Textiles', 1.0)
    >>> resolve_supplier("Golden Thread Company")[0]
    'Golden Thread'
    """
    scored = [(_ratio(raw, name), name) for name in supplier_names()]
    ratio, name = max(scored, key=lambda pair: (pair[0], pair[1]))
    return (name, ratio) if ratio >= _SUPPLIER_THRESHOLD else None


def resolve_material(raw: str) -> tuple[str, str] | None:
    """Resolve a material to the vocabulary.

    Returns ``("exact", canonical)`` for a vocabulary hit, ``("proposal",
    canonical)`` for a near-miss to review, or ``None`` when nothing is close.
    A near-miss is never applied silently (brief §12).

    >>> resolve_material("cotton")
    ('exact', 'cotton')
    >>> resolve_material("Organic cottn")
    ('proposal', 'organic cotton')
    """
    vocab = material_vocab()
    if raw.strip().lower() in vocab.canonical:
        return ("exact", raw.strip().lower())
    scored = [(_ratio(raw, name), name) for name in vocab.canonical]
    ratio, name = max(scored, key=lambda pair: (pair[0], pair[1]))
    return ("proposal", name) if ratio >= _MATERIAL_PROPOSAL_THRESHOLD else None


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class NormalizeResult:
    """The normalized records and the provenance the pass produced."""

    records: list[SourceRecord]
    events: list[RuleEvent]
    findings: list[Finding]


def _event(record_id: str, column: str, rule_id: str, source_type: SourceType, before: str, after: str) -> RuleEvent:
    return RuleEvent.create(
        record_id=record_id,
        column=column,
        rule_id=rule_id,
        rule_version="v1",
        source_type=source_type,
        value_before=before,
        value_after=after,
    )


def normalize_records(records: list[SourceRecord]) -> NormalizeResult:
    """Apply every normalization rule to each record, emitting events and findings.

    Deterministic and order-preserving: each record's rules run in a fixed order,
    a successful transform writes a :class:`RuleEvent`, and an uncertain material
    match writes a proposal :class:`Finding` rather than editing the value.
    """
    out_records: list[SourceRecord] = []
    events: list[RuleEvent] = []
    findings: list[Finding] = []

    for source in records:
        record = source.record
        raw = source.raw
        changes: dict[str, object] = {}

        # Coerce the amount fields; a parse failure leaves the cell null for the
        # validity detector to flag. Even a lossless coercion writes an event, so
        # no populated cell is without a rule (invariant 2).
        quantity = _to_int(raw["quantity"])
        if quantity is not None:
            changes["quantity"] = quantity
            events.append(
                _event(
                    record.record_id,
                    "quantity",
                    "amount_coerce",
                    SourceType.NORMALIZE_AMOUNT,
                    raw["quantity"],
                    str(quantity),
                )
            )
        price = _to_float(raw["unit_price"])
        if price is not None:
            changes["unit_price"] = price
            events.append(
                _event(
                    record.record_id,
                    "unit_price",
                    "amount_coerce",
                    SourceType.NORMALIZE_AMOUNT,
                    raw["unit_price"],
                    str(price),
                )
            )

        weight = parse_weight(raw["net_weight"])
        if weight is not None:
            changes["component_weight_g"] = weight
            events.append(
                _event(
                    record.record_id,
                    "component_weight_g",
                    "weight_to_grams",
                    SourceType.NORMALIZE_UNIT,
                    raw["net_weight"],
                    _grams_str(weight),
                )
            )

        pairs = parse_composition(raw["composition"])
        if pairs is not None:
            canonical = format_composition(pairs)
            changes["composition"] = canonical
            events.append(
                _event(
                    record.record_id,
                    "composition",
                    "composition_parse",
                    SourceType.NORMALIZE_COMPOSITION,
                    raw["composition"],
                    canonical,
                )
            )

        date = parse_date(raw["order_date"])
        if date is not None:
            changes["order_date"] = date
            events.append(
                _event(
                    record.record_id,
                    "order_date",
                    "date_iso",
                    SourceType.NORMALIZE_DATE,
                    raw["order_date"],
                    date.isoformat(),
                )
            )

        iso = resolve_country(raw["country"])
        if iso is not None:
            changes["factory_country_iso"] = iso
            events.append(
                _event(
                    record.record_id,
                    "factory_country_iso",
                    "country_iso",
                    SourceType.NORMALIZE_COUNTRY,
                    raw["country"],
                    iso,
                )
            )

        supplier = resolve_supplier(raw["supplier"])
        if supplier is not None:
            canonical_supplier, ratio = supplier
            changes["supplier_normalized"] = canonical_supplier
            events.append(
                RuleEvent.create(
                    record_id=record.record_id,
                    column="supplier_normalized",
                    rule_id="supplier_fuzzy",
                    rule_version="v1",
                    source_type=SourceType.NORMALIZE_SUPPLIER,
                    value_before=raw["supplier"],
                    value_after=canonical_supplier,
                    method_params={"ratio": round(ratio, 4)},
                )
            )

        material = resolve_material(raw["material"])
        if material is not None and material[0] == "exact":
            changes["material_normalized"] = material[1]
            events.append(
                _event(
                    record.record_id,
                    "material_normalized",
                    "material_vocab",
                    SourceType.NORMALIZE_MATERIAL,
                    raw["material"],
                    material[1],
                )
            )
        elif material is not None:  # proposal — surfaced, not applied
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="material_normalized",
                    category=AnomalyCategory.MAPPING,
                    severity=Severity.MEDIUM,
                    message=f"{raw['material']!r} near vocabulary {material[1]!r}",
                    proposed_value=material[1],
                    evidence={"column": "material_normalized", "raw_value": raw["material"]},
                )
            )

        out_records.append(dataclasses.replace(source, record=dataclasses.replace(record, **changes)))

    return NormalizeResult(records=out_records, events=events, findings=findings)


def _grams_str(grams: float) -> str:
    """Render grams without a trailing ``.0`` when whole."""
    return str(int(grams)) if grams == int(grams) else str(grams)


def _to_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None
