"""Render the interstitial panels of the review loop as HTML (pure, deterministic).

The upload form, the drift-gate decision, and the review queue are the three pages
the loop needs before the final footprint. Each is a pure function of a connector
result and returns an HTML string; the final result page is rendered by
``carbonara.view.render_view`` unchanged. The slate palette is imported from the
view so there is one palette source, not a second look.
"""

from __future__ import annotations

import html

from carbonara.ingest import IngestResult, IngestStatus
from carbonara.review import ReviewItem, ReviewQueue, ReviewStatus
from carbonara.view import CSS as _PALETTE  # the one palette source (slate dashboard)

__all__ = ["drift_panel", "page", "review_panel", "upload_form"]

#: Form controls the footprint view has no need for, in the same palette tokens.
_FORM_CSS = """
form.inline { display: inline; margin: 0; }
button, .btn { font-family: var(--mono); font-size: 12px; cursor: pointer;
  background: var(--panel); color: var(--ink); border: 1px solid var(--line);
  border-radius: 5px; padding: 6px 12px; }
button:hover, .btn:hover { border-color: var(--accent); }
button.primary { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
button.approve { border-color: var(--observed); color: var(--observed); }
button.reject { border-color: var(--flag); color: var(--flag); }
input[type=file] { font-family: var(--mono); font-size: 12px; color: var(--ink); }
.actions { display: flex; gap: 10px; margin-top: 16px; align-items: center; }
.step { color: var(--muted); font-size: 12px; margin-bottom: 20px; }
.status-accepted { color: var(--observed); } .status-review { color: var(--flag); }
.rename { color: var(--ink); } .rename b { color: var(--accent); font-weight: 400; }
td.st-approved { color: var(--observed); } td.st-rejected { color: var(--flag); }
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def page(step: str, body: str, *, title: str = "carbonara") -> str:
    """Wrap panel ``body`` in the full HTML document with the shared palette."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} · review console</title>
<style>{_PALETTE}{_FORM_CSS}</style>
</head><body>
<h1>{_esc(title)} — review console</h1>
<p class="step">{_esc(step)}</p>
{body}
</body></html>"""


def upload_form() -> str:
    """The landing panel: choose a CSV or XLSX file and submit it to the drift gate."""
    return """
<section class="panel">
  <h2>Upload a source file</h2>
  <p class="range">A vendor BOM (CSV or XLSX). It is admitted through the schema-drift
    gate before anything is computed — nothing is processed silently.</p>
  <form class="actions" method="post" action="/upload" enctype="multipart/form-data">
    <input type="file" name="file" accept=".csv,.xlsx" required>
    <button type="submit" class="primary">Admit</button>
  </form>
</section>"""


def drift_panel(ingest: IngestResult) -> str:
    """Show the drift-gate outcome and, on drift, the rename proposal to confirm.

    A clean file is ``ACCEPTED`` (empty mapping); a drifted file is
    ``REVIEW_REQUIRED`` with a proposed rename the reviewer confirms before the run
    — the proposal is never applied silently (§8.1). Editing the mapping by hand is
    out of scope for this surface; the one action is to accept the proposal.
    """
    accepted = ingest.status is IngestStatus.ACCEPTED
    status_cls = "status-accepted" if accepted else "status-review"
    proposal = ingest.mapping_proposal
    if proposal and proposal.renames:
        renames = "".join(
            f'<li class="rename">{_esc(src)} → <b>{_esc(dst)}</b></li>' for src, dst in proposal.renames.items()
        )
        body = f"<p class='range'>Proposed renames (confirm to apply):</p><ul>{renames}</ul>"
    elif accepted:
        body = "<p class='range'>Schema matches the expected contract — no rename needed.</p>"
    else:
        body = "<p class='range'>Drift with no confident rename proposal; nothing to auto-apply.</p>"
    unresolved = ""
    if proposal and (proposal.unresolved_added or proposal.unresolved_removed):
        added = ", ".join(proposal.unresolved_added) or "none"
        removed = ", ".join(proposal.unresolved_removed) or "none"
        unresolved = f"<p class='range'>Unresolved — added: {_esc(added)}; missing: {_esc(removed)}</p>"
    return f"""
<section class="panel">
  <h2>Drift gate · <span class="{status_cls}">{_esc(ingest.status.value)}</span></h2>
  <p class="range">content hash <b>{_esc(ingest.content_hash[:16])}</b> ·
    format {_esc(ingest.source_format.value)} · encoding {_esc(ingest.encoding)}</p>
  {body}
  {unresolved}
  <div class="actions">
    <form class="inline" method="post" action="/confirm">
      <button type="submit" class="primary">Confirm mapping &amp; run</button>
    </form>
    <form class="inline" method="post" action="/reset"><button type="submit">Start over</button></form>
  </div>
</section>"""


def _decision_button(item: ReviewItem, action: str, label: str, css: str) -> str:
    return (
        f'<form class="inline" method="post" action="/decide">'
        f'<input type="hidden" name="finding_id" value="{_esc(item.finding.finding_id)}">'
        f'<input type="hidden" name="action" value="{action}">'
        f'<button type="submit" class="{css}">{label}</button></form>'
    )


def _queue_row(item: ReviewItem) -> str:
    finding = item.finding
    status = item.status
    if status is ReviewStatus.PENDING:
        controls = (
            _decision_button(item, "approve", "approve", "approve")
            + " "
            + _decision_button(item, "reject", "reject", "reject")
        )
        status_cell = "<td>pending</td>"
    else:
        controls = "—"
        status_cell = f'<td class="st-{status.value}">{_esc(status.value)}</td>'
    return (
        f"<tr><td>{_esc(finding.record_id)}</td><td>{_esc(finding.column)}</td>"
        f"<td>{_esc(finding.category.value)}</td>"
        f'<td class="sev-{finding.severity.value}">{_esc(finding.severity.value)}</td>'
        f"<td>{_esc(finding.message)}</td><td>{_esc(finding.proposed_value or '—')}</td>"
        f"{status_cell}<td>{controls}</td></tr>"
    )


def review_panel(queue: ReviewQueue) -> str:
    """The review queue: every finding with its status and approve/reject controls.

    Approving a finding that carries a proposed value mints a correction the re-run
    re-applies; rejecting records the decision and leaves the cell as it arrived.
    Both are recorded through :class:`~carbonara.review.ReviewQueue` — the queue is
    the source of truth, this panel only renders it.
    """
    items = queue.items()
    pending = len(queue.pending())
    rows = "".join(_queue_row(item) for item in items)
    return f"""
<section class="panel wide">
  <h2>Review queue · {len(items)} findings · {pending} pending</h2>
  <div class="scroll"><table><thead><tr><th>record</th><th>column</th><th>category</th>
    <th>sev</th><th>finding</th><th>proposed</th><th>status</th><th>decide</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
  <div class="actions">
    <form class="inline" method="post" action="/rerun">
      <button type="submit" class="primary">Re-run with approvals</button>
    </form>
    <form class="inline" method="post" action="/reset"><button type="submit">Start over</button></form>
  </div>
</section>"""
