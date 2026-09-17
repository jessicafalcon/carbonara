"""The fill ladder routes each case to the correct tier, first match wins."""

from __future__ import annotations

from carbonara.contract import QualityStatus
from carbonara.fill import fill_weights
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records
from carbonara.rules import AnomalyCategory, Severity, SourceType


def _row(row_id: str, **over: str) -> dict[str, str]:
    row = {
        "source_row_id": row_id,
        "style_id": "TSH-1",
        "sku": f"SKU-{row_id}",
        "component": "shell fabric",
        "material": "cotton",
        "vendor": "Acme Textiles",
        "composition": "100% cotton",
        "net_weight": "150 g",
        "country": "Portugal",
        "order_date": "2024-01-08",
        "quantity": "10",
        "unit_price": "5.0",
    }
    row.update(over)
    return row


def _fill(rows: list[dict[str, str]]):
    return fill_weights(normalize_records(materialize(rows, {"vendor": "supplier"})).records)


def _by_id(records, source_row_id: int):
    return next(r for r in records if r.record.record_id == f"r{source_row_id:04d}")


def test_tight_group_fills_by_grouped_median():
    # Five tight cotton/shell/TSH observations, plus one blank to fill.
    rows = [_row(str(i), net_weight=w) for i, w in enumerate(["150 g", "152 g", "148 g", "151 g", "149 g"])]
    rows.append(_row("99", net_weight=""))
    result = _fill(rows)
    [event] = result.events
    assert event.source_type is SourceType.GROUPED_MEDIAN
    assert _by_id(result.records, 99).record.component_weight_g == 150.0
    assert event.uncertainty_range is not None


def test_high_spread_group_falls_through_to_reference_constant():
    spread = ["10 g", "300 g", "20 g", "500 g", "15 g", "600 g"]  # cv well over 0.30
    rows = [_row(str(i), net_weight=w) for i, w in enumerate(spread)]
    rows.append(_row("99", net_weight=""))
    result = _fill(rows)
    fill = next(e for e in result.events if e.record_id == "r0099")
    assert fill.source_type is SourceType.REFERENCE_CONSTANT
    assert fill.method_params["assumption"] is True


def test_sparse_group_falls_through_to_reference_constant():
    rows = [_row("1", net_weight="150 g"), _row("2", net_weight="152 g")]  # only two observations
    rows.append(_row("99", net_weight=""))
    result = _fill(rows)
    fill = next(e for e in result.events if e.record_id == "r0099")
    assert fill.source_type is SourceType.REFERENCE_CONSTANT


def test_component_without_a_reference_is_left_action_required():
    rows = [_row("1", component="mystery trim", net_weight="")]
    result = _fill(rows)
    assert result.events == []
    assert _by_id(result.records, 1).record.component_weight_g is None
    assert _by_id(result.records, 1).record.quality_status is QualityStatus.ACTION_REQUIRED
    # The residual null is surfaced for review — the completeness gap the ladder
    # could not resolve, not the missing weights it filled (§7.4 tier 5).
    [finding] = [f for f in result.findings if f.category is AnomalyCategory.COMPLETENESS]
    assert finding.column == "component_weight_g" and finding.severity is Severity.MEDIUM


def test_implausible_observed_weight_is_flagged_not_changed():
    rows = [_row("46", net_weight="5000 g")]
    result = _fill(rows)
    [finding] = [f for f in result.findings if f.category is AnomalyCategory.PLAUSIBILITY]
    assert finding.severity.value == "high"
    assert _by_id(result.records, 46).record.component_weight_g == 5000.0  # not changed
    assert _by_id(result.records, 46).record.quality_status is QualityStatus.FLAGGED
