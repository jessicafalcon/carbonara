"""Drive the review-console router through the loop with no socket and no clock."""

from __future__ import annotations

import pathlib

from webapp.app import handle
from webapp.session import Session

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_BOM_V1 = _ROOT / "fixtures" / "bom_v1.csv"
_BOUNDARY = "X-BOUND"
_CT = f"multipart/form-data; boundary={_BOUNDARY}"


def _upload_body(raw: bytes, filename: str = "bom_v1.csv") -> bytes:
    head = f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    return b"--" + _BOUNDARY.encode() + b"\r\n" + head + b"\r\n\r\n" + raw + b"\r\n--" + _BOUNDARY.encode() + b"--\r\n"


def _session(tmp_path) -> Session:
    return Session(store_root=tmp_path)


def test_landing_shows_the_upload_form(tmp_path):
    response = handle("GET", "/", _session(tmp_path))
    assert response.status == 200
    assert 'action="/upload"' in response.body


def test_upload_reports_the_drift_gate_decision(tmp_path):
    session = _session(tmp_path)
    handle("POST", "/upload", session, content_type=_CT, body=_upload_body(_BOM_V1.read_bytes()))
    response = handle("GET", "/", session)
    assert "review_required" in response.body  # the fixture's `vendor` header drifts
    assert "vendor → <b>supplier</b>" in response.body


def test_confirm_runs_the_pipeline_and_shows_the_review_queue(tmp_path):
    session = _session(tmp_path)
    handle("POST", "/upload", session, content_type=_CT, body=_upload_body(_BOM_V1.read_bytes()))
    response = handle("POST", "/confirm", session)
    assert "Review queue" in response.body
    assert session.queue is not None and len(session.queue.items()) > 0
    # the planted `Organic cottn` typo surfaces as a mapping proposal, not a silent fix
    assert "organic cotton" in response.body


def test_unknown_route_is_404(tmp_path):
    assert handle("GET", "/nope", _session(tmp_path)).status == 404
