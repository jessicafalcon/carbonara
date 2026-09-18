"""The pure request router for the review console: (request, session) -> Response.

``handle`` is a pure function of the request and the session — no socket, no clock
(the run/decision timestamps are injected constants), no network. It writes the
upload to the session's store and calls ``carbonara`` functions; it holds no
business logic of its own. ``scripts/serve.py`` is the only part that binds a port.
"""

from __future__ import annotations

import dataclasses
import pathlib
import urllib.parse

from carbonara.apply_review import applications_from
from carbonara.ingest import admit, read_source
from carbonara.pipeline import run
from carbonara.review import ReviewQueue
from carbonara.view import render_view
from webapp.multipart import parse_multipart
from webapp.render import drift_panel, page, review_panel, upload_form
from webapp.session import Session

__all__ = ["CREATED_AT", "DECIDED_AT", "Response", "handle"]

#: Injected, never wall-clock — the same file + decisions render byte-identically (§8.2).
CREATED_AT = "2026-01-01T00:00:00Z"
DECIDED_AT = "2026-01-01T00:00:00Z"
_ACTOR = "reviewer"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Response:
    """One rendered HTTP response: a status and an HTML (or plain) body."""

    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"


def handle(method: str, path: str, session: Session, *, content_type: str = "", body: bytes = b"") -> Response:
    """Route one request to the connector and render the resulting panel.

    ``GET /`` shows the current step (upload form, drift gate, or queue). The POST
    routes each advance the loop and return the next panel directly: ``/upload``
    admits the file, ``/confirm`` runs the pipeline and builds the queue,
    ``/decide`` records one approve/reject, ``/rerun`` re-runs with the approvals
    and renders the footprint, ``/reset`` clears the session.
    """
    if method == "GET" and path == "/":
        return _current(session)
    if method == "POST" and path == "/upload":
        return _upload(session, content_type, body)
    if method == "POST" and path == "/confirm":
        return _confirm(session)
    if method == "POST" and path == "/decide":
        return _decide(session, body)
    if method == "POST" and path == "/rerun":
        return _rerun(session)
    if method == "POST" and path == "/reset":
        session.reset()
        return _current(session)
    return Response(status=404, body="not found", content_type="text/plain; charset=utf-8")


def _current(session: Session) -> Response:
    """Render whichever step the session has reached (resumable on a plain GET)."""
    if session.queue is not None:
        return Response(status=200, body=page(_STEP_QUEUE, review_panel(session.queue)))
    if session.ingest is not None:
        return Response(status=200, body=page(_STEP_DRIFT, drift_panel(session.ingest)))
    return Response(status=200, body=page(_STEP_UPLOAD, upload_form()))


def _upload(session: Session, content_type: str, body: bytes) -> Response:
    _, files = parse_multipart(content_type, body)
    upload = files.get("file")
    if upload is None or not upload[1]:
        return _current(session)  # nothing selected — fall back to the upload form
    filename, raw = upload
    stored = session.store_root / pathlib.Path(filename).name  # .name strips any path in the field
    stored.write_bytes(raw)
    session.reset()
    result = admit(stored, session.store_root, rerun=True)
    session.raw = raw
    session.content_hash = result.content_hash
    session.ingest = result
    return _current(session)


def _confirm(session: Session) -> Response:
    if session.raw is None or session.ingest is None:
        return _current(session)
    proposal = session.ingest.mapping_proposal
    mapping = dict(proposal.renames) if proposal else {}
    _, rows, _ = read_source(session.raw, session.ingest.source_format)
    result = run(rows, mapping, content_hash=session.content_hash or "", created_at=CREATED_AT)
    session.mapping = mapping
    session.queue = ReviewQueue(result.findings)
    return _current(session)


def _decide(session: Session, body: bytes) -> Response:
    if session.queue is None:
        return _current(session)
    form = urllib.parse.parse_qs(body.decode("utf-8"))
    finding_id = form.get("finding_id", [""])[0]
    action = form.get("action", [""])[0]
    if finding_id and action in ("approve", "reject"):
        decide = session.queue.approve if action == "approve" else session.queue.reject
        decide(finding_id, actor=_ACTOR, at=DECIDED_AT)
    return _current(session)


def _rerun(session: Session) -> Response:
    if session.raw is None or session.ingest is None or session.queue is None:
        return _current(session)
    _, rows, _ = read_source(session.raw, session.ingest.source_format)
    result = run(
        rows,
        session.mapping or {},
        content_hash=session.content_hash or "",
        created_at=CREATED_AT,
        approvals=applications_from(session.queue),
    )
    return Response(status=200, body=render_view(result, title="carbonara"))


_STEP_UPLOAD = "Step 1 — upload a source file."
_STEP_DRIFT = "Step 2 — schema-drift gate. Confirm the mapping to run the pipeline."
_STEP_QUEUE = "Step 3 — review queue. Approve or reject findings, then re-run."
