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
from webapp.app import handle
from webapp.session import Session

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_BOUNDARY = "X-BOUND"
_CT = f"multipart/form-data; boundary={_BOUNDARY}"
_FOCUS = "r0065"


def _upload_body(raw: bytes) -> bytes:
    head = b'Content-Disposition: form-data; name="file"; filename="bom_v1.csv"'
    return b"--" + _BOUNDARY.encode() + b"\r\n" + head + b"\r\n\r\n" + raw + b"\r\n--" + _BOUNDARY.encode() + b"--\r\n"


def _uploaded_and_confirmed(tmp_path) -> Session:
    session = Session(store_root=tmp_path)
    handle("POST", "/upload", session, content_type=_CT, body=_upload_body(_BOM_V1.read_bytes()))
    handle("POST", "/confirm", session)
    return session


def _trace(body: str) -> dict:
    """Extract the embedded provenance JSON from a render_view result page."""
    marker = '<script id="trace-data" type="application/json">'
    start = body.index(marker) + len(marker)
    end = body.index("</script>", start)
    return json.loads(body[start:end].replace("<\\/", "</"))


def _focus_mapping_finding_id(session: Session) -> str:
    assert session.queue is not None
    for item in session.queue.items():
        finding = item.finding
        if finding.record_id == _FOCUS and finding.category is AnomalyCategory.MAPPING:
            return finding.finding_id
    raise AssertionError(f"no mapping finding for {_FOCUS}")


def test_empty_approvals_leaves_the_typo_uncosted(tmp_path):
    session = _uploaded_and_confirmed(tmp_path)
    result = handle("POST", "/rerun", session)
    assert "catalog footprint" in result.body
    assert _FOCUS not in _trace(result.body)  # unresolved material is not costed


def test_approving_the_mapping_resolves_and_chains_the_cell(tmp_path):
    session = _uploaded_and_confirmed(tmp_path)
    finding_id = _focus_mapping_finding_id(session)
    body = urllib.parse.urlencode({"finding_id": finding_id, "action": "approve"}).encode()
    handle("POST", "/decide", session, body=body)

    result = handle("POST", "/rerun", session)
    trace = _trace(result.body)
    assert _FOCUS in trace  # now costed
    assert trace[_FOCUS]["material"] == "organic cotton"
    # the approval chains onto the normalize source rather than clobbering it (§8.1)
    lineage = trace[_FOCUS]["material_lineage"]
    assert len(lineage) == 2
    assert [tier["source_type"] for tier in lineage] == ["normalize_material", "reference_resolve"]


def test_rerun_is_byte_identical_on_the_same_decisions(tmp_path):
    session = _uploaded_and_confirmed(tmp_path)
    finding_id = _focus_mapping_finding_id(session)
    body = urllib.parse.urlencode({"finding_id": finding_id, "action": "approve"}).encode()
    handle("POST", "/decide", session, body=body)
    first = handle("POST", "/rerun", session).body
    second = handle("POST", "/rerun", session).body
    assert first == second
