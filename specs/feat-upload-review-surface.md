# feat — a live upload → review → re-run surface (backlog item 4)

Branch `feat/upload-review-surface`, off `main`. The brief describes "a thin,
clean full-stack surface"; the shipped artifact is a static HTML render
(`carbonara/view.py`, `scripts/build_view.py`) plus a narrated CLI walkthrough
(`scripts/demo.py`). This item makes the interactive loop real: upload a file, see
the drift-gate decision, work the review queue (approve/reject), re-run, and read
the chained-cell lineage in the re-run's provenance drawer.

Backlog item 4 carries no per-item spec by default; this file exists at the user's
request because item 4 is the largest backlog item. The BACKLOG item-4 entry records
the outcome and this deviation.

## Objective

A small web surface that is a **pure view/transport** over `pipeline.run` and
`review.ReviewQueue` — no business logic. The connector stays the single source of
truth: `admit`, `run`, `ReviewQueue`, `apply_review.applications_from`, and
`view.render_view` already assemble this loop deterministically in `scripts/demo.py`
and `scripts/build_view.py`. Not in the data path — determinism and provenance live
in `run`, not the transport (carbonara-correctness).

## Design decisions

- **Stack: stdlib `http.server`.** `ThreadingHTTPServer` + `BaseHTTPRequestHandler`,
  server-rendered HTML, plain form POSTs. Zero new dependencies, offline — on the
  portability bar. No client framework: upload / approve / reject / re-run are
  ordinary form submissions, and `render_view` already ships its provenance drawer
  as vanilla JS. Multipart upload is parsed with a small stdlib helper (`cgi` was
  removed in 3.13). Flask/FastAPI (new heavy deps), a JSON-API + JS client (more
  moving parts, still needs the server), and HTMX (a vendored client dep for no
  gain) all lose to it here.
- **Code lives outside `carbonara/`.** A new top-level `webapp/` package, like
  `analytics/`, so the determinism guard's domain stays the connector alone while
  the transport is importable and unit-testable. `webapp/` is not part of the built
  wheel (`module-root` builds only `carbonara`), so `pyproject.toml` is unchanged.
- **Scope: the full four-step loop.** Upload → drift-gate decision + confirm mapping
  → review queue approve/reject → re-run showing the chained lineage. Deferred (not
  this PR): cross-restart persistence (in-process session state only),
  auth / multi-user / concurrency, and hand-editing the mapping — the drift gate's
  proposed rename is shown with a one-click accept, since `run()` needs a confirmed
  mapping.
- **Styling: reuse the slate-dashboard palette.** The same tokens as
  `carbonara/view.py` (slate bg, teal accent, Space Grotesk), so the new panels read
  as one tool — one palette source, not a second look.
- **Reproducibility: the timestamp is injected at the I/O boundary.** `handle`
  takes a `now` for the run's `created_at` and a decision's `at`; it reads no clock.
  `scripts/serve.py` (which already owns the socket) passes wall-clock per request,
  so a live reviewer's provenance carries the real time; the tests pass a fixed
  constant for determinism. `render_view` does not render `created_at`, so a live
  re-run of the same file and decisions is byte-identical regardless of the clock —
  the byte-identical property comes from `run_id` (content hash + versions), not
  from freezing the timestamp. This mirrors why `run` refuses to read the clock:
  the timestamp *policy* belongs at the boundary, not in the pure router.

## Approach

`webapp/` is a pure transport with one small mutable session holder:

- `webapp/multipart.py` — parse one `multipart/form-data` body into fields + the
  uploaded file bytes, stdlib only.
- `webapp/session.py` — a `Session` holding in-process state: uploaded raw bytes /
  content hash, the `IngestResult` (status + `mapping_proposal`), the confirmed
  `mapping`, and the `ReviewQueue`. No I/O, no clock.
- `webapp/render.py` — pure HTML helpers for the three new panels (upload form,
  drift-gate panel, review-queue table with approve/reject controls), reusing the
  `view.py` palette. The result page reuses `view.render_view` unchanged.
- `webapp/app.py` — the pure router `handle(method, path, headers, body, session)
  → Response(status, content_type, body)`. Routes: `GET /` (current state),
  `POST /upload` (multipart → `admit`), `POST /confirm` (mapping from the proposal →
  `run` → findings → `ReviewQueue`), `POST /decide` (`approve`/`reject`),
  `POST /rerun` (`run(approvals=applications_from(queue))` → `render_view`),
  `POST /reset`.
- `scripts/serve.py` — the launcher: a `BaseHTTPRequestHandler` that reads the
  request and delegates to `app.handle`, served by `ThreadingHTTPServer` on a port
  from argv (default 8000). Does the socket / I/O the connector must not.

### Reuse (do not reinvent)

- `carbonara.ingest.admit` — upload → drift gate + mapping proposal.
- `carbonara.pipeline.run` / `PipelineResult` — the single deterministic pass.
- `carbonara.review.ReviewQueue` (`approve`, `reject`, `pending`, `items`).
- `carbonara.apply_review.applications_from` — queue → approvals for the re-run.
- `carbonara.view.render_view` + its palette — the result page + shared styling.

## Steps (one commit each, green before the next)

1. **Spec** — this file.
2. **`webapp/` foundation.** `multipart.py`, `session.py`, and `render.py` (upload
   form + drift-gate panel), reusing the slate palette. Unit tests for the parser
   and the pure render helpers.
3. **Router: upload + confirm.** `webapp/app.py` with `GET /`, `POST /upload`,
   `POST /confirm`. Tests drive `handle()` through upload → drift gate → confirm →
   review queue on `fixtures/bom_v1.csv`.
4. **Review + re-run.** The review-queue panel, `POST /decide`, and `POST /rerun`
   rendering `render_view`. Tests through the full loop: approve the planted
   `Organic cottn` mapping, assert the re-run resolves and costs the cell and the
   drawer carries the two-entry chained lineage; empty approvals reproduces the
   single-pass output.
5. **Launcher.** `scripts/serve.py` (`BaseHTTPRequestHandler` → `app.handle`,
   `ThreadingHTTPServer`).
6. **README.** A short section documenting the surface and its run command.

## Testing

Drive the pure `handle()` router directly — no socket bound, no clock read —
through the whole loop, on the fixture BOM. Fully offline and deterministic,
honoring the no-network-in-tests rule (carbonara-tests). Determinism is asserted by
re-invoking `handle` twice on the same inputs and comparing the rendered bytes.

## Dependencies

None. Everything is stdlib (`http.server`, `email`/manual multipart parsing) plus
the connector's own modules. `pyproject.toml` is unchanged.

## Exit gate

`uv run pytest` + `uv run pre-commit run --all-files` clean; run `/simplify` and fix
what it finds; push the branch and open the PR; stop — the merge is the user's call.
Update CLAUDE.md Current status after the PR.
