"""The webapp transport's parser and pure render helpers (offline, no socket)."""

from __future__ import annotations

import pathlib

from carbonara.ingest import IngestResult, IngestStatus, SourceFormat
from carbonara.review import ReviewQueue
from carbonara.rules import AnomalyCategory, Finding, Severity
from carbonara.source_schema import MappingProposal
from tests.webapp_multipart import CONTENT_TYPE, multipart_body
from webapp.multipart import parse_multipart
from webapp.render import drift_panel, review_panel, upload_form


def test_parse_multipart_splits_file_and_field_and_preserves_bytes():
    # A CSV with an embedded comma and an internal newline must survive byte-for-byte.
    csv = b'id,note\r\n1,"a,b"\r\n2,plain\r\n'
    body = multipart_body(
        [
            (b'Content-Disposition: form-data; name="file"; filename="bom.csv"', csv),
            (b'Content-Disposition: form-data; name="action"', b"admit"),
        ]
    )
    fields, files = parse_multipart(CONTENT_TYPE, body)
    assert fields == {"action": "admit"}
    assert files["file"] == ("bom.csv", csv)


def _review_ingest() -> IngestResult:
    return IngestResult(
        content_hash="deadbeef" * 8,
        source_format=SourceFormat.CSV,
        status=IngestStatus.REVIEW_REQUIRED,
        stored_path=pathlib.Path("raw/deadbeef.csv"),
        mapping_proposal=MappingProposal(renames={"vendor": "supplier"}, unresolved_added=(), unresolved_removed=()),
    )


def test_upload_form_posts_to_the_drift_gate():
    html = upload_form()
    assert 'action="/upload"' in html
    assert 'enctype="multipart/form-data"' in html


def test_drift_panel_shows_the_proposed_rename_and_a_confirm_action():
    html = drift_panel(_review_ingest())
    assert "review_required" in html
    assert "vendor → <b>supplier</b>" in html
    assert 'action="/confirm"' in html


def test_review_panel_shows_both_controls_and_marks_the_active_decision():
    finding = Finding.create(
        record_id="r0065",
        column="material_normalized",
        category=AnomalyCategory.MAPPING,
        severity=Severity.MEDIUM,
        message="'Organic cottn' near 'organic cotton'",
        proposed_value="organic cotton",
        evidence={"raw_value": "Organic cottn"},
    )
    queue = ReviewQueue([finding])
    pending_html = review_panel(queue)
    assert 'value="approve"' in pending_html and 'value="reject"' in pending_html
    assert 'action="/rerun"' in pending_html

    # An approved finding keeps both buttons; the approve control is marked active.
    queue.approve(finding.finding_id, actor="reviewer", at="2026-01-01T00:00:00Z")
    decided_html = review_panel(queue)
    assert "st-approved" in decided_html
    assert 'class="approve active"' in decided_html
    assert 'value="reject"' in decided_html  # still offered, so the reviewer can flip
    assert "1 approved" in decided_html
