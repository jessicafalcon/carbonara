"""Shared records for every data-augmentation rule: transformations and findings.

Normalization and (later) imputation are the same kind of object — a versioned
deterministic rule that writes a :class:`RuleEvent` (brief §7.1). A problem to
decide, rather than a value that changed, is a :class:`Finding`.
"""

from __future__ import annotations

import dataclasses
import enum

__all__ = [
    "AnomalyCategory",
    "Finding",
    "RuleEvent",
    "Severity",
    "SourceType",
]


class SourceType(enum.StrEnum):
    """The provenance kind of a value (brief §8.1).

    Phase 3 emits the ``NORMALIZE_*`` family; the fill-ladder tiers
    (``DERIVED_FORMULA``, ``GROUPED_MEDIAN``, …) are added when Phase 4 needs them.

    >>> SourceType.NORMALIZE_UNIT
    <SourceType.NORMALIZE_UNIT: 'normalize_unit'>
    """

    NORMALIZE_DATE = "normalize_date"
    NORMALIZE_UNIT = "normalize_unit"
    NORMALIZE_AMOUNT = "normalize_amount"
    NORMALIZE_COMPOSITION = "normalize_composition"
    NORMALIZE_COUNTRY = "normalize_country"
    NORMALIZE_SUPPLIER = "normalize_supplier"
    NORMALIZE_MATERIAL = "normalize_material"
    UNKNOWN = "unknown"


class Severity(enum.StrEnum):
    """How much a finding should worry a reviewer."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnomalyCategory(enum.StrEnum):
    """The kind of problem a finding reports (brief §7.3).

    ``MAPPING`` is an uncertain resolution (a proposed alias), not an error —
    surfaced for review rather than applied.
    """

    VALIDITY = "validity"
    COMPLETENESS = "completeness"
    DUPLICATE_KEY = "duplicate_key"
    CROSS_FIELD = "cross_field"
    DISTRIBUTION = "distribution"
    MAPPING = "mapping"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class RuleEvent:
    """One rule application: what a rule changed, on which cell, and by which version.

    Ids are composite and deterministic — one rule touches one cell once per pass,
    so ``record_id:column:rule_id`` is stable across runs (no clock, no counter).

    >>> event = RuleEvent.create(
    ...     record_id="r0007", column="component_weight_g", rule_id="unit_to_grams",
    ...     rule_version="v1", source_type=SourceType.NORMALIZE_UNIT,
    ...     value_before="0.42 kg", value_after="420",
    ... )
    >>> event.event_id
    'r0007:component_weight_g:unit_to_grams'
    >>> event.is_original_null
    False
    """

    event_id: str
    record_id: str
    column: str
    rule_id: str
    rule_version: str
    source_type: SourceType
    value_before: str | None
    value_after: str | None
    is_original_null: bool
    method_params: dict[str, object] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        column: str,
        rule_id: str,
        rule_version: str,
        source_type: SourceType,
        value_before: str | None,
        value_after: str | None,
        method_params: dict[str, object] | None = None,
    ) -> RuleEvent:
        """Build an event, deriving the id and ``is_original_null`` from the inputs."""
        return cls(
            event_id=f"{record_id}:{column}:{rule_id}",
            record_id=record_id,
            column=column,
            rule_id=rule_id,
            rule_version=rule_version,
            source_type=source_type,
            value_before=value_before,
            value_after=value_after,
            is_original_null=value_before is None or value_before == "",
            method_params=method_params or {},
        )


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Finding:
    """A problem or uncertain mapping to review — never an applied edit.

    ``column`` is ``None`` for a row-level finding (e.g. a duplicate key).
    ``proposed_value`` is set for a ``MAPPING`` finding a reviewer may approve.

    >>> finding = Finding.create(
    ...     record_id="r0042", column="material_normalized",
    ...     category=AnomalyCategory.MAPPING, severity=Severity.MEDIUM,
    ...     message="'Organic cottn' near 'cotton'", proposed_value="cotton",
    ... )
    >>> finding.finding_id
    'r0042:material_normalized:mapping'
    """

    finding_id: str
    record_id: str
    column: str | None
    category: AnomalyCategory
    severity: Severity
    message: str
    proposed_value: str | None = None
    evidence: dict[str, object] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        column: str | None,
        category: AnomalyCategory,
        severity: Severity,
        message: str,
        proposed_value: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> Finding:
        """Build a finding, deriving its deterministic id."""
        return cls(
            finding_id=f"{record_id}:{column or '-'}:{category.value}",
            record_id=record_id,
            column=column,
            category=category,
            severity=severity,
            message=message,
            proposed_value=proposed_value,
            evidence=evidence or {},
        )
