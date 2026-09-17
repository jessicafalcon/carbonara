"""Each anomaly detector fires on the case it is meant to catch."""

from __future__ import annotations

from carbonara.anomalies import detect_anomalies
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records
from carbonara.rules import AnomalyCategory, Severity


def _row(row_id: str, **over: str) -> dict[str, str]:
    row = {
        "source_row_id": row_id,
        "style_id": "TSH-1",
        "sku": f"SKU-{row_id}",
        "component": "shell",
        "material": "cotton",
        "vendor": "Acme Textiles",
        "composition": "100% cotton",
        "net_weight": "200 g",
        "country": "Portugal",
        "order_date": "2024-01-08",
        "quantity": "10",
        "unit_price": "5.0",
    }
    row.update(over)
    return row


def _findings(rows: list[dict[str, str]]):
    return detect_anomalies(normalize_records(materialize(rows, {"vendor": "supplier"})).records)


def _categories(findings, category):
    return [f for f in findings if f.category is category]


def test_malformed_date_is_a_validity_finding():
    findings = _categories(_findings([_row("1", order_date="2024-13-07")]), AnomalyCategory.VALIDITY)
    assert findings and findings[0].column == "order_date"


def test_zero_weight_with_positive_value_is_high_severity_cross_field():
    findings = _categories(_findings([_row("1", net_weight="0 g")]), AnomalyCategory.CROSS_FIELD)
    assert findings and findings[0].severity is Severity.HIGH


def test_duplicate_key_flags_the_repeat_only():
    rows = [_row("1", sku="DUP"), _row("2", sku="DUP")]  # same style/sku/component
    findings = _categories(_findings(rows), AnomalyCategory.DUPLICATE_KEY)
    assert len(findings) == 1  # first kept, repeat flagged — no double counting


def test_extreme_price_is_a_distribution_finding():
    prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    rows = [_row(str(i), unit_price=str(p)) for i, p in enumerate(prices)]
    rows.append(_row("99", unit_price="9999.0"))
    findings = _categories(_findings(rows), AnomalyCategory.DISTRIBUTION)
    assert any(f.column == "unit_price" and f.record_id == "r0099" for f in findings)


def test_unresolved_country_is_a_completeness_finding():
    findings = _categories(_findings([_row("1", country="")]), AnomalyCategory.COMPLETENESS)
    assert any(f.column == "factory_country_iso" for f in findings)


def test_missing_weight_is_not_flagged_here():
    # Weight completeness is owned by the fill stage (residual only), not detected here.
    findings = _categories(_findings([_row("1", net_weight="")]), AnomalyCategory.COMPLETENESS)
    assert not any(f.column == "component_weight_g" for f in findings)


def test_composition_not_summing_to_100_is_cross_field():
    findings = _categories(
        _findings([_row("1", composition="80% cotton / 30% polyester")]), AnomalyCategory.CROSS_FIELD
    )
    assert findings and findings[0].column == "composition"


def test_negative_quantity_is_a_validity_finding():
    findings = _categories(_findings([_row("1", quantity="-5")]), AnomalyCategory.VALIDITY)
    assert any(f.column == "quantity" and f.severity is Severity.HIGH for f in findings)
