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
    """A reusable rule minted from an approved mapping — a versioned alias."""

    rule_id: str
    rule_version: str
    source_type: SourceType
    key: str
    value: str


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
        """Mint a versioned alias rule from each approved mapping proposal."""
        rules: list[ApprovedRule] = []
        for item in self._items.values():
            finding = item.finding
            if item.status is ReviewStatus.APPROVED and finding.category is AnomalyCategory.MAPPING:
                rules.append(
                    ApprovedRule(
                        rule_id=f"alias:{finding.evidence['raw_value']}",
                        rule_version="v1",
                        source_type=SourceType.NORMALIZE_MATERIAL,
                        key=str(finding.evidence["raw_value"]),
                        value=str(finding.proposed_value),
                    )
                )
        return rules
