"""§12 normalization/anomaly cases, exercised end-to-end on fixtures/bom_v1.csv."""

from __future__ import annotations

import csv
import pathlib

import pytest

from carbonara.anomalies import detect_anomalies
from carbonara.materialize import materialize
from carbonara.normalize import NormalizeResult, normalize_records
from carbonara.rules import AnomalyCategory, Finding, Severity

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _run() -> tuple[NormalizeResult, list[Finding]]:
    # The vendor→supplier mapping is the approved Phase 2 proposal.
    result = normalize_records(materialize(_rows(), {"vendor": "supplier"}))
    return result, detect_anomalies(result.records)


@pytest.fixture(scope="module")
def pipeline() -> tuple[NormalizeResult, list[Finding]]:
    return _run()


def _record(result: NormalizeResult, source_row_id: int):
    return next(sr for sr in result.records if sr.record.record_id == f"r{source_row_id:04d}")


def _findings_for(findings: list[Finding], source_row_id: int, category: AnomalyCategory) -> list[Finding]:
    rid = f"r{source_row_id:04d}"
    return [f for f in findings if f.record_id == rid and f.category is category]


def test_composition_shorthand_parses_to_canonical(pipeline):
    result, _ = pipeline
    assert _record(result, 12).record.composition == "70% cotton / 30% polyester"


def test_mixed_units_convert_to_grams_and_preserve_raw(pipeline):
    result, _ = pipeline
    source = _record(result, 135)
    assert source.record.component_weight_g == 490.0
    assert source.raw["net_weight"] == "0.49 kg"  # raw preserved


def test_material_typo_is_a_proposal_not_applied(pipeline):
    result, _ = pipeline
    assert _record(result, 145).record.material_normalized is None
    proposals = [f for f in result.findings if f.record_id == "r0145"]
    assert proposals and proposals[0].proposed_value == "organic cotton"


def test_supplier_variant_normalizes_to_canonical(pipeline):
    result, _ = pipeline
    assert _record(result, 15).record.supplier_normalized == "Acme Textiles"


def test_malformed_date_is_a_validity_finding(pipeline):
    _, findings = pipeline
    assert _findings_for(findings, 41, AnomalyCategory.VALIDITY)


def test_extreme_price_is_a_distribution_finding(pipeline):
    _, findings = pipeline
    assert _findings_for(findings, 236, AnomalyCategory.DISTRIBUTION)


def test_zero_weight_positive_value_is_high_severity(pipeline):
    _, findings = pipeline
    cross = _findings_for(findings, 26, AnomalyCategory.CROSS_FIELD)
    assert cross and cross[0].severity is Severity.HIGH


def test_duplicate_key_is_flagged_once(pipeline):
    _, findings = pipeline
    assert _findings_for(findings, 307, AnomalyCategory.DUPLICATE_KEY)


def test_pass_is_reproducible():
    first, first_findings = _run()
    second, second_findings = _run()
    assert first.events == second.events
    assert first.findings == second.findings
    assert first_findings == second_findings
    assert [sr.record for sr in first.records] == [sr.record for sr in second.records]
