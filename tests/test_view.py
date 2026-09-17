"""The view renders deterministically and embeds a trace to source + factor version."""

from __future__ import annotations

import csv
import json
import pathlib
import re

import pytest

from carbonara.fill import fill_weights
from carbonara.footprint import factor_diff
from carbonara.ingest import content_hash
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records
from carbonara.pipeline import PipelineResult, run
from carbonara.view import render_view

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"


def _rows() -> list[dict[str, str]]:
    with _BOM_V1.open(newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def result() -> PipelineResult:
    return run(
        _rows(),
        {"vendor": "supplier"},
        content_hash=content_hash(_BOM_V1.read_bytes()),
        created_at="2026-01-01T00:00:00Z",
    )


def _trace(html: str) -> dict:
    payload = re.search(r'<script id="trace-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert payload is not None
    return json.loads(payload.group(1).replace("<\\/", "</"))


def test_render_is_byte_identical_across_runs(result):
    assert render_view(result) == render_view(result)


def test_page_shows_the_run_signature_and_panels(result):
    html = render_view(result)
    assert result.run_id in html
    for heading in ("Readiness", "Review queue", "Footprint", "Components"):
        assert heading in html


def test_trace_carries_rules_source_row_and_factor_version(result):
    trace = _trace(render_view(result))
    costed = next(c for c in result.footprint.components if c.estimated_kgco2e is not None)
    entry = trace[costed.record_id]
    assert entry["source_row_id"] == costed.record_id.lstrip("r").lstrip("0")
    assert entry["factor_source_version"] == "ecoinvent-3.9.1 via Ecobalyse"
    assert any(e["source_type"] == "derived_formula" for e in entry["events"])


def test_factor_diff_panel_appears_only_when_supplied(result):
    filled = fill_weights(normalize_records(materialize(_rows(), {"vendor": "supplier"})).records)
    diff = factor_diff(filled.records, filled.events, from_version="v1", to_version="v2")
    assert "Factor revision" not in render_view(result)
    assert "Factor revision" in render_view(result, diff=diff)
