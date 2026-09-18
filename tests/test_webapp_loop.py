"""The full review loop through the router: approve → re-run → chained lineage.

The planted `Organic cottn` typo (record r0065) arrives unresolved, so it is not
costed. Approving its mapping and re-running resolves and costs the cell, and its
material lineage chains (normalize → reference-resolve) rather than clobbering.
Everything is asserted from the router's rendered output — no socket, no clock.
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse

from carbonara.rules import AnomalyCategory
from tests.webapp_multipart import CONTENT_TYPE, upload_body
from webapp.app import handle
from webapp.session import Session

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_AT = "2026-01-01T00:00:00Z"  # a fixed injected timestamp keeps the tests deterministic
_FOCUS = "r0065"


def _uploaded_and_confirmed(tmp_path) -> Session:
    session = Session(store_root=tmp_path)
    handle("POST", "/upload", session, now=_AT, content_type=CONTENT_TYPE, body=upload_body(_BOM_V1.read_bytes()))
    handle("POST", "/confirm", session, now=_AT)
    return session


def _trace(body: str) -> dict:
    """Extract the embedded provenance JSON from a render_view result page."""
    marker = '<script id="trace-data" type="application/json">'
    start = body.index(marker) + len(marker)
    end = body.index("</script>", start)
    return json.loads(body[start:end].replace("<\\/", "</"))


def _reject(session, finding_id: str) -> None:
    body = urllib.parse.urlencode({"finding_id": finding_id, "action": "reject"}).encode()
    handle("POST", "/decide", session, now=_AT, body=body)


def _mapping_finding_ids(session) -> list[str]:
    assert session.queue is not None
    return [i.finding.finding_id for i in session.queue.items() if i.finding.category is AnomalyCategory.MAPPING]


def test_confirm_defaults_all_findings_approved_so_the_mapping_costs_and_chains(tmp_path):
    # No manual decision: confirm pre-approves every finding (item 11), so the mapping
    # is applied on re-run and the cell resolves, costs, and chains its lineage.
    session = _uploaded_and_confirmed(tmp_path)
    result = handle("POST", "/rerun", session, now=_AT)
    trace = _trace(result.body)
    assert _FOCUS in trace  # costed by the default approval
    assert trace[_FOCUS]["material"] == "organic cotton"
    # the approval chains onto the normalize source rather than clobbering it (§8.1)
    lineage = trace[_FOCUS]["material_lineage"]
    assert [tier["source_type"] for tier in lineage] == ["normalize_material", "reference_resolve"]


def test_rejecting_the_mapping_leaves_the_typo_uncosted(tmp_path):
    # The Organic cottn mapping is a reusable alias, so its finding recurs across the
    # matching cells; rejecting all of them means no alias is applied, leaving r0065
    # unresolved and uncosted (the opposite of the default-approved path above).
    session = _uploaded_and_confirmed(tmp_path)
    for finding_id in _mapping_finding_ids(session):
        _reject(session, finding_id)
    result = handle("POST", "/rerun", session, now=_AT)
    assert "catalog footprint" in result.body
    assert _FOCUS not in _trace(result.body)


def test_rerun_is_byte_identical_on_the_same_decisions(tmp_path):
    session = _uploaded_and_confirmed(tmp_path)
    first = handle("POST", "/rerun", session, now=_AT).body
    second = handle("POST", "/rerun", session, now=_AT).body
    assert first == second
