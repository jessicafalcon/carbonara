"""The review queue: approve or reject findings, keep the history, mint rules."""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable

from carbonara.rules import AnomalyCategory, Finding, SourceType

__all__ = ["ApprovedRule", "ReviewDecision", "ReviewItem", "ReviewQueue", "ReviewStatus"]


class ReviewStatus(enum.StrEnum):
    """Where a finding stands after review."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ReviewDecision:
    """One approve/reject action. ``at`` is injected, never read from the clock."""

    status: ReviewStatus
    actor: str
    note: str | None = None
    at: str | None = None


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ReviewItem:
    """A finding with its ordered decision history."""

    finding: Finding
    decisions: tuple[ReviewDecision, ...] = ()

    @property
    def status(self) -> ReviewStatus:
        """The current status — the last decision, or pending if none was made."""
        return self.decisions[-1].status if self.decisions else ReviewStatus.PENDING

    def with_decision(self, decision: ReviewDecision) -> ReviewItem:
        """Return a new item with the decision appended (history is never rewritten)."""
        return dataclasses.replace(self, decisions=(*self.decisions, decision))


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ApprovedRule:
    """A versioned correction minted from an approved finding.

    A ``MAPPING`` approval is a reusable alias: ``key`` is the raw value it
    matches, so one approval corrects every cell spelled that way. Any other
    approved finding that carries a ``proposed_value`` is a per-cell correction
    keyed to its ``record_id``, with ``key`` left ``None``.
    """

    rule_id: str
    rule_version: str
    source_type: SourceType
    record_id: str
    column: str
    value: str
    key: str | None = None


class ReviewQueue:
    """Hold findings for review, record decisions, and mint rules from approvals.

    >>> from carbonara.rules import Finding, AnomalyCategory, Severity
    >>> finding = Finding.create(
    ...     record_id="r0065", column="material_normalized",
    ...     category=AnomalyCategory.MAPPING, severity=Severity.MEDIUM,
    ...     message="'Organic cottn' near 'organic cotton'", proposed_value="organic cotton",
    ...     evidence={"raw_value": "Organic cottn"},
    ... )
    >>> queue = ReviewQueue([finding])
    >>> [item.status for item in queue.pending()]
    [<ReviewStatus.PENDING: 'pending'>]
    >>> _ = queue.approve(finding.finding_id, actor="reviewer")
    >>> queue.get(finding.finding_id).status
    <ReviewStatus.APPROVED: 'approved'>
    >>> queue.approved_rules()[0].key, queue.approved_rules()[0].value
    ('Organic cottn', 'organic cotton')
    """

    def __init__(self, findings: Iterable[Finding]) -> None:
        self._items: dict[str, ReviewItem] = {finding.finding_id: ReviewItem(finding=finding) for finding in findings}

    def items(self) -> tuple[ReviewItem, ...]:
        """Every item, in insertion order."""
        return tuple(self._items.values())

    def pending(self) -> tuple[ReviewItem, ...]:
        """Items with no decision yet."""
        return tuple(item for item in self._items.values() if item.status is ReviewStatus.PENDING)

    def get(self, finding_id: str) -> ReviewItem:
        """The item for a finding id."""
        return self._items[finding_id]

    def decide(
        self, finding_id: str, *, status: ReviewStatus, actor: str, note: str | None = None, at: str | None = None
    ) -> ReviewItem:
        """Record a decision, appending to the item's history."""
        decision = ReviewDecision(status=status, actor=actor, note=note, at=at)
        updated = self._items[finding_id].with_decision(decision)
        self._items[finding_id] = updated
        return updated

    def approve(self, finding_id: str, *, actor: str, note: str | None = None, at: str | None = None) -> ReviewItem:
        """Approve a finding."""
        return self.decide(finding_id, status=ReviewStatus.APPROVED, actor=actor, note=note, at=at)

    def reject(self, finding_id: str, *, actor: str, note: str | None = None, at: str | None = None) -> ReviewItem:
        """Reject a finding."""
        return self.decide(finding_id, status=ReviewStatus.REJECTED, actor=actor, note=note, at=at)

    def approved_rules(self) -> list[ApprovedRule]:
        """Mint a versioned correction from each approved finding that proposes a value.

        A ``MAPPING`` approval becomes a reusable alias (matched by raw value); any
        other approved finding carrying a ``proposed_value`` becomes a per-cell
        correction. An approved flag with no ``proposed_value`` mints nothing — there
        is no value to re-apply, and we never guess one (brief §15).
        """
        rules: list[ApprovedRule] = []
        for item in self._items.values():
            finding = item.finding
            if item.status is not ReviewStatus.APPROVED:
                continue
            value, column = finding.proposed_value, finding.column
            if value is None or column is None:
                continue
            rules.append(_rule_from_finding(finding, value=value, column=column))
        return rules


def _rule_from_finding(finding: Finding, *, value: str, column: str) -> ApprovedRule:
    """Build the correction rule for one approved finding.

    A ``MAPPING`` finding yields a reusable alias keyed to the raw value; anything
    else yields a per-cell correction keyed to the finding's record. Both resolve
    to a value against a reviewer decision, so both carry ``REFERENCE_RESOLVE``.
    """
    if finding.category is AnomalyCategory.MAPPING:
        raw = str(finding.evidence["raw_value"])
        return ApprovedRule(
            rule_id=f"alias:{raw}",
            rule_version="v1",
            source_type=SourceType.REFERENCE_RESOLVE,
            record_id=finding.record_id,
            column=column,
            value=value,
            key=raw,
        )
    return ApprovedRule(
        rule_id=f"approve:{finding.finding_id}",
        rule_version="v1",
        source_type=SourceType.REFERENCE_RESOLVE,
        record_id=finding.record_id,
        column=column,
        value=value,
        key=None,
    )
