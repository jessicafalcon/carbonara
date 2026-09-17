"""Detect anomalies as reviewable findings — never silent edits (brief §7.3)."""

from __future__ import annotations

import math
import statistics
from collections import Counter

from carbonara.materialize import SourceRecord
from carbonara.normalize import parse_composition
from carbonara.rules import AnomalyCategory, Finding, Severity

__all__ = ["detect_anomalies"]

#: Modified z-score cutoff (median/MAD on log values) for a distribution outlier.
_MAD_THRESHOLD = 3.5
_MAD_SCALE = 0.6745
#: A composition's fractions must sum to 1.0 within this tolerance.
_COMPOSITION_TOLERANCE = 0.001


def _validity(records: list[SourceRecord]) -> list[Finding]:
    findings: list[Finding] = []
    for source in records:
        record = source.record
        if source.raw["order_date"].strip() and record.order_date is None:
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="order_date",
                    category=AnomalyCategory.VALIDITY,
                    severity=Severity.MEDIUM,
                    message=f"unparseable date {source.raw['order_date']!r}",
                )
            )
        if record.quantity is not None and record.quantity < 0:
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="quantity",
                    category=AnomalyCategory.VALIDITY,
                    severity=Severity.HIGH,
                    message=f"negative quantity {record.quantity}",
                )
            )
    return findings


def _completeness(records: list[SourceRecord]) -> list[Finding]:
    findings: list[Finding] = []
    for source in records:
        record = source.record
        if record.component_weight_g is None:
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="component_weight_g",
                    category=AnomalyCategory.COMPLETENESS,
                    severity=Severity.LOW,
                    message="missing weight",
                )
            )
        if record.factory_country_iso is None:
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="factory_country_iso",
                    category=AnomalyCategory.COMPLETENESS,
                    severity=Severity.LOW,
                    message="unresolved country",
                )
            )
    return findings


def _duplicate_key(records: list[SourceRecord]) -> list[Finding]:
    keys = [(s.record.style_id, s.record.sku, s.record.component) for s in records]
    counts = Counter(keys)
    findings: list[Finding] = []
    seen: Counter[tuple[str, str, str]] = Counter()
    for source, key in zip(records, keys, strict=True):
        seen[key] += 1
        if counts[key] > 1 and seen[key] > 1:  # flag repeats, keep the first for counting
            findings.append(
                Finding.create(
                    record_id=source.record.record_id,
                    column=None,
                    category=AnomalyCategory.DUPLICATE_KEY,
                    severity=Severity.MEDIUM,
                    message=f"duplicate (style, sku, component) {key}",
                )
            )
    return findings


def _cross_field(records: list[SourceRecord]) -> list[Finding]:
    findings: list[Finding] = []
    for source in records:
        record = source.record
        positive_value = (record.quantity or 0) > 0 or (record.unit_price or 0) > 0
        if record.component_weight_g == 0 and positive_value:
            findings.append(
                Finding.create(
                    record_id=record.record_id,
                    column="component_weight_g",
                    category=AnomalyCategory.CROSS_FIELD,
                    severity=Severity.HIGH,
                    message="zero weight on a line with positive value",
                )
            )
        pairs = parse_composition(source.raw["composition"])
        if pairs is not None:
            total = sum(fraction for fraction, _ in pairs)
            if abs(total - 1.0) > _COMPOSITION_TOLERANCE:
                findings.append(
                    Finding.create(
                        record_id=record.record_id,
                        column="composition",
                        category=AnomalyCategory.CROSS_FIELD,
                        severity=Severity.MEDIUM,
                        message=f"composition sums to {round(total * 100)}%, not 100%",
                    )
                )
    return findings


def _distribution(records: list[SourceRecord], column: str, values: list[tuple[str, float]]) -> list[Finding]:
    positive = [(record_id, value) for record_id, value in values if value > 0]
    if len(positive) < 3:
        return []
    logs = [math.log(value) for _, value in positive]
    median = statistics.median(logs)
    mad = statistics.median([abs(x - median) for x in logs])
    if mad == 0:
        return []
    findings: list[Finding] = []
    for (record_id, value), x in zip(positive, logs, strict=True):
        if _MAD_SCALE * abs(x - median) / mad > _MAD_THRESHOLD:
            findings.append(
                Finding.create(
                    record_id=record_id,
                    column=column,
                    category=AnomalyCategory.DISTRIBUTION,
                    severity=Severity.MEDIUM,
                    message=f"extreme {column} {value}",
                    evidence={"value": value},
                )
            )
    return findings


def detect_anomalies(records: list[SourceRecord]) -> list[Finding]:
    """Run every detector over the normalized records, in a fixed order."""
    weights = [
        (s.record.record_id, s.record.component_weight_g) for s in records if s.record.component_weight_g is not None
    ]
    prices = [(s.record.record_id, s.record.unit_price) for s in records if s.record.unit_price is not None]
    return [
        *_validity(records),
        *_completeness(records),
        *_duplicate_key(records),
        *_cross_field(records),
        *_distribution(records, "component_weight_g", weights),
        *_distribution(records, "unit_price", prices),
    ]
