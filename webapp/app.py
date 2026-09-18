"""The request router for the review console: (request, session, now) -> Response.

``handle`` is deterministic given the session's store and the injected ``now``
timestamp — it reads no clock and binds no socket; it writes the upload into the
session's store, calls ``carbonara`` functions, and renders their results. It holds
no business logic of its own. The timestamp policy lives at the I/O boundary that
owns the clock — ``scripts/serve.py`` passes wall-clock, the tests pass a fixed
constant — mirroring why ``pipeline.run`` refuses to read the clock itself (§8.2).
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

__all__ = ["Response", "handle"]

_ACTOR = "reviewer"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Response:
    """One rendered HTTP response: a status and an HTML (or plain) body."""

    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"


def handle(
    method: str, path: str, session: Session, *, now: str, content_type: str = "", body: bytes = b""
) -> Response:
    """Route one request to the connector and render the resulting panel.

    ``now`` is the injected timestamp for this request — the run's ``created_at``
    and a decision's ``at``. ``GET /`` shows the current step (upload form, drift
    gate, or queue). The POST routes each advance the loop and return the next panel
    directly: ``/upload`` admits the file, ``/confirm`` runs the pipeline and builds
    the queue, ``/decide`` records one approve/reject, ``/rerun`` re-runs with the
    approvals and renders the footprint, ``/reset`` clears the session.
    """
    if method == "GET" and path == "/":
        return _current(session)
    if method == "POST" and path == "/upload":
        return _upload(session, content_type, body)
    if method == "POST" and path == "/confirm":
        return _confirm(session, now)
    if method == "POST" and path == "/decide":
        return _decide(session, body, now)
    if method == "POST" and path == "/rerun":
        return _rerun(session, now)
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
    session.ingest = result
    _, session.rows, _ = read_source(raw, result.source_format)  # parse once; confirm/rerun reuse it
    return _current(session)


def _confirm(session: Session, now: str) -> Response:
    if session.ingest is None or session.rows is None:
        return _current(session)
    proposal = session.ingest.mapping_proposal
    mapping = dict(proposal.renames) if proposal else {}
    result = run(session.rows, mapping, content_hash=session.ingest.content_hash, created_at=now)
    session.mapping = mapping
    session.queue = ReviewQueue(result.findings)
    return _current(session)


def _decide(session: Session, body: bytes, now: str) -> Response:
    if session.queue is None:
        return _current(session)
    form = urllib.parse.parse_qs(body.decode("utf-8"))
    finding_id = form.get("finding_id", [""])[0]
    action = form.get("action", [""])[0]
    if finding_id and action in ("approve", "reject"):
        decide = session.queue.approve if action == "approve" else session.queue.reject
        decide(finding_id, actor=_ACTOR, at=now)
    return _current(session)


def _rerun(session: Session, now: str) -> Response:
    if session.ingest is None or session.rows is None or session.queue is None:
        return _current(session)
    result = run(
        session.rows,
        session.mapping or {},
        content_hash=session.ingest.content_hash,
        created_at=now,
        approvals=applications_from(session.queue),
    )
    return Response(status=200, body=render_view(result, title="carbonara"))


_STEP_UPLOAD = "Step 1 — upload a source file."
_STEP_DRIFT = "Step 2 — schema-drift gate. Confirm the mapping to run the pipeline."
_STEP_QUEUE = "Step 3 — review queue. Approve or reject findings, then re-run."
