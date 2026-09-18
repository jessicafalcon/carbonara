# CLAUDE.md

Session instructions for the carbonara connector. Read this first, every session.
The full design and the phase plan live in [PROJECT-BRIEF.md](PROJECT-BRIEF.md)
(§16 is the phase-by-phase build plan); this file is *how we work*, not *what we
build*.

## Repo map

```text
carbonara/        the connector package (the data path — kept deterministic)
tests/            cross-module + README/behavior tests
references/       versioned reference/factor CSVs, one citation per row
fixtures/         generated fixtures + retained ground truth
specs/            one spec per phase, named after its branch (specs/<branch>.md)
PROJECT-BRIEF.md  the design + phased build plan (§16)
CLAUDE.md         this file — the session workflow
.claude/skills/   the build-standard skills (below)
.claude/hooks/    determinism guard + ruff-on-edit (fire automatically)
pyproject.toml    uv/ruff/ty/pytest config     uv.lock  pinned deps
```

## Core principles (in priority order)

1. **Determinism first.** Same input + same rule versions ⇒ byte-identical
   output, lineage, and ledger. No LLM, no unseeded randomness, no wall-clock, no
   env reads in `carbonara/`. This outranks everything else — a faster or shorter
   change that breaks it does not land. (`carbonara-correctness` §1; the
   determinism guard enforces it on edit.)
2. **Portability.** Runs on any machine with `uv` and Python ≥ 3.11, offline.
   Deps pinned in `uv.lock`; reference data versioned in-repo; no absolute paths,
   no machine-specific config, no network in the data path or the tests. Prefer
   stdlib and already-installed deps over new ones.
3. **Results backed by data.** Every published number traces to a rule, a source
   row, and a factor version (ledger + Bloodline spine). Filled values carry an
   uncertainty range; fill accuracy is *measured* against ground truth, never
   claimed. Stay inside the claims boundaries (brief §15).
4. **Clean code, tested, version-controlled.** Small single-concern modules,
   typed, one runnable check per non-trivial unit, small green commits. This is
   the house baseline, not a nice-to-have.

## Communication

- **Result first:** what changed / passed / failed, then the details.
- Plain English, short sentences. No task restatement, no "I will now…", no
  closing summary that repeats the middle.
- One sentence if it fits; explanations ≤ 4 sentences.
- **Report after a task:** files touched, commands run, result, open risks, next
  step — nothing else.

## The build harness

### Skills — launch the matching one *before* the work

| Skill | Launch before… |
|---|---|
| `carbonara-craft` | writing/refactoring any Python, choosing a dependency |
| `carbonara-correctness` | landing anything in the data path, adding a rule, reviewing |
| `carbonara-tests` | writing or changing any test |
| `carbonara-voice` | writing a commit, PR, comment/docstring, or any `.md` file |
| `carbonara-pr` | opening or finalizing a phase PR (structure/process; pairs with `carbonara-voice`) |
| `carbonara-efficiency` | fan-out reads, wiring an external source, long multi-turn work |

### Hooks — fire automatically, no action needed

- **ruff-on-edit** (PostToolUse, any `*.py`): formats + lint-fixes the edited file.
- **determinism-guard** (PostToolUse, `carbonara/*.py`): blocks LLM calls,
  unseeded randomness, wall-clock, `uuid4`, and env reads in the connector
  package. If it fires on legitimately non-deterministic code, that code belongs
  *outside* `carbonara/` (a generator or script), or the value should be injected.

## Git workflow — one branch + one PR per phase or backlog item

The §16 phases are complete; ongoing work is the [BACKLOG.md](BACKLOG.md) items.
Both run on the **same one-branch-one-PR rule** — the phase rules below are the
baseline, and the [Backlog items](#backlog-items-post-16-work) subsection at the
end notes where a backlog item differs (no per-item spec; decisions recorded in
the backlog, not a spec).

- **Phase 0 was committed directly to `main`** (repo bootstrap). From **Phase 1
  on, every phase gets its own branch and one PR.**
- Branch name: `phase-<n>-<slug>` (e.g. `phase-1-contract-and-fixture`).
- **Start a phase (local):**
  ```sh
  git switch main && git pull --ff-only
  git switch -c phase-<n>-<slug>
  ```
- **Spec first, as actionable steps.** Break the phase into an ordered list of
  actionable steps in `specs/phase-<n>-<slug>.md` (mirrors brief §16, authored
  with `carbonara-voice`), before implementation. The spec is the first step and
  its own commit. **Write it as a senior data architect:** choose the simplest,
  most elegant solution that meets the contract — boring over clever — and cut
  anything speculative. No overengineering.
- **Record every design or decision change in the spec.** The spec stays the
  source of truth. If a choice changes mid-phase — the approach, a dependency, a
  scope cut, an interface, a deferral — update `specs/phase-<n>-<slug>.md` (or the
  brief §16 entry when the phase has not started) in the same commit as the change,
  authored with `carbonara-voice`. A decision that lives only in the chat or the
  code is a decision the next session cannot see.
- **One step = one commit.** Work the phase step by step; each step is a single
  atomic commit, made once it is green (`uv run pytest` + `uv run pre-commit run
  --all-files` clean). Never bundle a whole phase into one commit; never commit
  red or unrelated changes together.
- **At the exit gate.** When the brief §16 exit gate is green, run `/simplify` on
  the branch (a reuse/simplification pass — catches a hand-rolled branch stdlib
  already covers, a redundant assertion, dead code — before a reviewer has to),
  fix what it finds, then push the branch and open/finalize the PR
  (`carbonara-voice`), then **stop — do not merge. The merge to `main` is the
  user's call.** Push and PRs are fine at any point; only the merge waits for the
  user.
- **Update Current status after every PR and every merge** (in the same change) —
  the phase, branch, open PR, and the next spec step. A new session resumes from
  it, so it must be current.
- Confirm before force-push, history rewrite, or anything else hard to undo.

### Backlog items (post-§16 work)

Ongoing work is the [BACKLOG.md](BACKLOG.md) items. Each runs on the **same
one-branch-one-PR rule as a phase**, with two differences: the backlog entry *is*
the spec (no `specs/<branch>.md` file), and a mid-build decision change is
recorded in `BACKLOG.md`, not a spec.

- **Pick the next item** from the BACKLOG.md build-order table — top-down by
  default, respecting the `Depends on` column. One item = one branch = one PR.
- **Branch name:** `<type>/<slug>`, the type matching the change — `feat/…` for a
  data-path or behavior item, `refacto/…` / `perf/…` / `docs/…` otherwise (e.g.
  `feat/category-in-contract`, `refacto/closed-form-split`). Same house types as
  commits (`carbonara-voice`).
- **Start (local):** `git switch main && git pull --ff-only`, then
  `git switch -c <type>/<slug>`.
- **No per-item spec.** The BACKLOG.md entry already carries what to change, why,
  where in the code, and whether it touches the data path — that is the spec.
  Read it, then work the item step by step, one atomic commit per green step
  (same commit rules and gates as a phase: `uv run pytest` + `uv run pre-commit
  run --all-files` clean).
- **Record decision changes in BACKLOG.md.** If a choice changes mid-build — a
  dependency, a scope cut, an interface, a deferral — update that item's entry in
  `BACKLOG.md` in the same commit as the change (`carbonara-voice`). The backlog
  stays the source of truth; a decision that lives only in chat or code is lost to
  the next session.
- **Exit gate, PR, merge, status: identical to a phase.** The data-path and
  correctness bars still apply (determinism guard, `carbonara-correctness`); at
  the exit push the branch, open/finalize the PR, and **stop — the merge is the
  user's call**; update Current status after every PR and merge.

### Commit best practices

- **Atomic.** One logical change per commit — the step, nothing bundled in.
- **Commit often**, each time a step is green; small commits are easier to read,
  review, and revert.
- **Never commit broken or unrelated code.**
- **Subject:** imperative, present tense, ≤ 50 characters, no trailing period —
  "Add contract dataclass", not "Added…" or "Fixes bug…". The house
  `type(scope): summary` form and the `Co-Authored-By` trailer are in
  `carbonara-voice`.
- **Body (only when it adds something):** a blank line, then *what* changed and
  *why* (and any side effects) — not *how*; the diff already shows how.
- **Footer:** reference the phase PR or issue when relevant (`Refs #<n>`).

## How the tooling fires across a phase

1. Read this file + the brief's phase section; recall project memory.
2. Branch off `main` (local); write `specs/<branch>.md` as an ordered list of
   actionable steps (launch `carbonara-voice`) — the spec is the first commit.
3. Work step by step — launch `carbonara-craft` / `carbonara-correctness` /
   `carbonara-tests` as you go; the PostToolUse hooks run on every `.py` edit.
4. Each step, once green (`uv run pytest`, then `uv run pre-commit run
   --all-files`): one atomic commit.
5. At the exit gate: run `/simplify` on the branch and fix what it finds, then
   push the branch, open/finalize the PR, and stop — the user merges. Update
   Current status once told it's merged.

For a **backlog item**, step 2 has no spec file — read the item's BACKLOG.md
entry instead, branch `<type>/<slug>` off `main`, and record any mid-build
decision change in that entry. Steps 3–5 are unchanged. See
[Backlog items](#backlog-items-post-16-work).

## Project tooling

```sh
uv sync                              # install deps + dev tools (ruff, ty, pytest, pre-commit)
uv run pytest                        # unit tests + doctests (incl. README)
uv run ruff format . && uv run ruff check --fix .
uv run ty check .
uv run pre-commit run --all-files    # uv-lock, ruff, ty
pre-commit install --hook-type pre-push   # run the gate on push (once, local)
```

Effort: run Opus 4.8 at **xhigh** for this project's coding/agentic work.

## Current status

- **Phase 0 — build harness + repo skeleton: done** (on `main`).
- **Phase 1 — contract + fixture generator: done** (merged, PR #2).
- **Phase 2 — ingest + schema-drift gate: done** (merged, PR #3).
- **Phase 3 — normalize + validate + anomaly events: done** (merged, PR #4).
- **Phase 4 — fill ladder + rule ledger + Bloodline lineage: done** (merged, PR #5).
- **Phase 5 — footprint + brand-facing view + provenance drawer: done** (merged, PR #6).
  Footprint costs `weight_kg × factor(material)` with factor source/version, mapping
  confidence, observed-vs-filled share, and an uncertainty range; each estimate carries
  a ledger event + Bloodline source; unresolved material is flagged (not costed).
  Exact Ecobalyse `cch` factors (`scripts/fetch_factors.py`, token-gated), reference-data
  content-hashing in the run id (`reference_digest`), the slate-dashboard view
  (`carbonara/view.py`), and the trace journey all landed.
- **Phase 6 — (stretch) two-vintage change explanation: done** (merged, PR #7).
  Branch `phase-6-lea-and-icanexplain`; spec + 8 steps committed. The v1→v2 change in a
  **production-weighted** catalog total `F = Σ mass_kg × factor` (quantity does not enter
  the Phase-5 per-line footprint, so a real volume effect needs this new mart aggregate)
  is decomposed with **icanexplain** into an intensity effect (the polyester factor bump)
  and a volume/mix effect (production mass + the cotton→organic-cotton shift), reconciled
  to the observed delta and validated against planted ground truth. The **v2 (2025)**
  vintage is a deterministic transform of v1's clean skeleton (per-archetype volume
  multiplier + named mix shift + 2025 stamp); `fixtures/generate.py` writes `bom_v2`,
  `ground_truth_v2`, and `decomposition_truth.csv`. A new `analytics/` package (outside
  `carbonara/`, heavier deps in an `analytics` group) runs both vintages through the
  pipeline, a tiny staging→core→mart **DuckDB SQL DAG** rolls per-line footprints up to
  `F` by material×vintage, and `analytics/explain.py` decomposes + reconciles;
  `scripts/build_explanation.py` writes the artifact. Exit gate green: reconciliation is
  exact, the intensity effect sits on polyester alone and equals the planted factor bump,
  and pipeline vs ground truth agree in direction and within ~10% (the residual is
  propagated fill error, reported as QA). Planting runs before the volume/mix transform,
  so both vintages corrupt the same cells and fill error cancels in the delta. **Lea (`lea-cli`) not adopted** — hard `sqlglot` conflict
  with icanexplain's ibis + BigQuery dependency bloat; the DAG is plain DuckDB SQL (see
  the spec's Dependencies section). Added a `carbonara-pr` PR-writing skill. `pytest`
  (172) + `pre-commit` pass.
- **Phase 7 — (aspiration) Bloodline augmentation-rule helper (M7): done** (merged, PR #8).
  Branch `phase-7-augmentation-rule-helper`; spec + 4 steps committed. Closes the
  source-vs-lifecycle gap (§8.1): the in-repo helper `carbonara/augment.py`
  (`RuleRecord`, `augment_source`, `augment_lineage`, `lineage_history`) preserves a
  cell's original Bloodline lineage while attaching an ordered rule record (rule
  id/version, inputs, confidence) inside the head `Source`'s metadata — one `Source`
  per cell kept, lifecycle as an oldest-first `"lineage"` list, no parallel store, no
  clobber. Uses `apply_data_lineage`/`Source` as intended and depends only on
  Bloodline + pandas + stdlib, so it is liftable upstream (no upstream PR this phase,
  per §11). Deterministic → lives in `carbonara/`, passes the guard. The live pipeline
  still clobbers with `override=True` (one rule per cell today); the helper is
  demonstrated on a two-rule cell (`tests/test_augment.py`, 7 regression tests) and a
  module + README doctest. Also fixed a pre-existing E501 in
  `scripts/build_explanation.py` that slipped past PR #7's gate, added a CI workflow
  (`.github/workflows/ci.yml`: `pytest` + `pre-commit` on push/PR) since the gate was
  only ever local, and installed the pre-push hook. `pytest` (181) + `pre-commit`
  pass.
- **Phase 8 — demo + limitations note, review loop applied (M8): done** (merged, PR #9).
  Branch `phase-8-applied-review-loop`; spec + 8 steps committed. Wires
  `review.approved_rules()` back into the pipeline as a deterministic second pass
  (`carbonara/apply_review.py`): an approved mapping (`Organic cottn` → `organic cotton`)
  is re-applied to the cell it corrects and chained onto the cell's normalize source
  via `augment_lineage` (normalize_material → reference_resolve, not clobber; §8.1),
  writing a ledger event like any rule (§8.2). The decision (actor/status/`at`) is
  injected as an `approvals` param on `pipeline.run()` — no clock, passes the guard —
  and the pass slots in right after normalize so the three planted `Organic cottn`
  cells flow into fill + footprint (unresolved → costed). Scope **broader** (confirmed):
  `approved_rules` generalized to any approved finding with a `proposed_value` (MAPPING
  stays a reusable alias, others per-cell); review decisions persist/replay as JSONL
  (`fixtures/review_decisions.jsonl`); the static view marks resolved findings "applied"
  and the drawer shows the chained spine lineage; `scripts/demo.py` is the narrated
  eight-step walkthrough; README has doctested `Walkthrough` + `Limitations` (§15)
  sections. Two bounded cuts recorded in the spec — generalization keyed to
  `proposed_value` (no invented per-category semantics), view stays static HTML.
  Exit gate green: walkthrough reproducible from a clean checkout; the approved cell
  carries a two-entry lineage (original + approval); re-run byte-identical; empty
  approvals reproduces the single-pass output. `pytest` (203) + `pre-commit` pass.
  Phase 8 was the last §16 phase — **the build is complete.**
- **Post-project audit follow-ups: done** (merged, PR #10). Branch
  `chore/audit-followups` off `main`, no connector behavior change. Corrects three stale spec claims
  against the shipped code (Phase 1 row count ~300 not ~500; Phase 5 excludes
  plausibility-`FLAGGED` weights from headline totals; Phase 6 ground-truth
  validation is direction-only with the ~10% gap reported as QA), labels the
  footprint as a material-stage estimate (README + brief §9/§15), fixes the
  README quickstart (real `uv` path, not the unpublished `pip install`), and
  renames the four phase-named test suites to behavior names. `pytest` (203) +
  `pre-commit` pass. Two follow-ups deferred to their own branches (data-path /
  error-behavior changes): wire `detect_anomalies` into `pipeline.run` (the ~119
  findings the live pipeline never surfaces) + a view stage-boundary caption; and
  input-boundary hardening (crashes → reviewable findings). **Merge is the user's
  call.**
- **Wire the anomaly net into the pipeline: done** (merged, PR #11). Branch
  `feat/wire-anomaly-net` off `main`; spec `specs/feat-wire-anomaly-net.md` + steps
  committed. Closes the resilience-audit gap: `detect_anomalies` (validity,
  completeness, duplicate-key, cross-field, distribution) was called only from
  tests, so `pipeline.run` surfaced 7 findings on the fixture while ~119 planted
  anomalies passed through silently — against §7.3. `run` now calls it on the
  pre-fill records (missing-weight must fire before the ladder fills the cell) and
  folds the findings in after the normalize findings; additive and deterministic
  (categories disjoint from mapping/plausibility so ids can't collide, `run_id`
  unaffected, re-run reproduces). Weight completeness is flagged on the *residual*
  (the null the ladder leaves, `fill.py`, MEDIUM), not on every originally-missing
  cell — the raw form flooded the queue with 97 already-filled items and buried the
  actionable ones, while the unfillable weights raised no finding at all;
  `detect_anomalies` keeps country completeness. The view gains a by-severity
  summary (§10) and the material-stage caption (fixture queue 123 → 26: 2 high /
  24 medium / 0 low); the demo names the split (`6 mappings + 23 anomalies`); a new
  test proves the §12 cases surface through `run()`, not only `detect_anomalies`.
  `pytest` (210) + `pre-commit` pass.
- **Input-boundary hardening: at exit gate, awaiting merge.** Branch
  `feat/input-boundary-hardening` off `main`; spec
  `specs/feat-input-boundary-hardening.md` + steps committed. Closes the second
  half of the resilience audit — the messy input the connector accepts raised raw
  tracebacks. Now: `ingest._read_csv` decodes UTF-8 → CP1252 (Western vendor files
  never crash) and records the encoding on the result + registry; `materialize`
  validates the row schema and raises `SourceSchemaError` naming a missing required
  column or a non-integer `source_row_id` instead of a raw `KeyError`/`ValueError`;
  `run` surfaces a high-severity "source has no data rows" finding for a header-only
  file (was a silent 0 kgCO₂e). A wrong path stays a loud `FileNotFoundError` (a
  caller error, deliberately not dignified as data). Deterministic — fixed decode
  order, `content_hash`/`run_id` unchanged. `pytest` (214) + `pre-commit` pass.
  **Done** (merged, PR #12).
- **Harness tweak (direct to `main`):** `ruff-on-edit.sh` now runs
  `ruff check --fix --unfixable F401`, so a not-yet-used import is no longer
  deleted mid-edit (it broke add-import-then-use edit sequences). F401 is still
  reported by the hook (non-blocking) and still removed by the pre-commit gate
  (`ruff-check --fix`), so nothing unused reaches a commit.
- **§16 build complete; now working the backlog.** [BACKLOG.md](BACKLOG.md) landed
  on `main` (merged, PR #13) — an ordered list of six post-project items (build
  order in its table). Backlog items follow the
  [Backlog items](#backlog-items-post-16-work) workflow: one branch + one PR each,
  the backlog entry as the spec, decisions recorded in `BACKLOG.md`.
  - **Item 1 — category into the contract: done** (merged, PR #15). Required `str`
    field resolved in `materialize` (`derive_category`), parallel to `record_id`;
    both `_category` splits deleted; `fill`/`footprint` read `record.category`.
  - **Item 2 — parse XLSX: done** (merged, PR #16). `ingest._read_xlsx` (openpyxl,
    not `pandas.read_excel`) converts each cell to the CSV-path string faithfully;
    `read_rows`/`read_source` are the shared readers; `openpyxl` is the one new dep.
  - **Item 3 — run a real messy file end to end: done** (merged, PR #18). A real
    U.S. textile-import CSV (`samples/us_textile_imports_by_fiber.csv`, USDA ERS /
    Census trade data) runs through `scripts/real_file_exercise.py`: the drift gate
    refuses the non-BOM shape and the normalizers resolve/flag real values without
    crashing. Exercise only (lives in `scripts/`, not the QA suite). A follow-up
    search found real apparel data *does* exist (NPCGA) but was blocked by format —
    which items 7 and 8 then closed. Findings in `samples/README.md`.
  - **Item 7 — parse semicolon-delimited (European) CSVs + item 8 — material
    synonyms: done** (merged, PR #19). Branch `feat/semicolon-csv-reader`. Item 7:
    `ingest._detect_delimiter` picks `;` vs `,` from the header (deterministic),
    unlocking NPCGA. Item 8: a versioned `aliases` column resolves `polyamide →
    nylon` exactly (an ambiguous `"polyamide or nylon"` stays a review proposal).
    Together they drive `scripts/npcga_footprint.py` — a real material-stage
    footprint (157.2 kgCO₂e over 200 real garments, 116 costed) from real fibre +
    weight data (`samples/npcga_subset.csv`, CC BY-SA 4.0).
  - **Workflow tweak (merged, PR #17):** run `/simplify` before opening a PR.
  - **Item 7/8 follow-ups (also on PR #19, both done):** a UTF-8 BOM reader
    (`_decode` uses `utf-8-sig`); and **item 9** — `wool` (28.9) and `acrylic`
    (11.1) factors fetched from Ecobalyse via `fetch_factors.py` (the pinned eight
    unchanged) and added to the vocabulary, so they now cost in the NPCGA run.
    `silk` stays unmapped — it is not in Ecobalyse's library and was not invented.
  - **Item 5 — replace icanexplain with the closed-form split: done** (merged,
    PR #20). Branch `refacto/closed-form-split`.
    `analytics/explain.decompose` computes both effects from the mart directly
    (`intensity = mass_from × (factor_to − factor_from)` per material, volume/mix the
    remainder), so reconciliation holds by arithmetic. The whole `analytics`
    dependency group was removed (icanexplain + its ibis stack + pyarrow, only there
    for the ibis arrow bridge) — the layer needs nothing beyond pandas + duckdb; the
    DuckDB DAG is unchanged. `pytest` (223) + `pre-commit` pass with the deps
    uninstalled. Decision recorded in BACKLOG item 5.
  - **Item 6 — use the augment lifecycle in the live pipeline: done** (merged,
    PR #21). Branch `feat/augment-in-pipeline`. Fixed the shared
    spine, not one call site: `apply_lineage` writes a cell's first rule as a plain
    head Source, then chains any further rule on that cell via `augment_lineage`
    (oldest first), so the lifecycle matches the ledger instead of clobbering (§8.1).
    Scope decision: no live cell is touched by more than one rule today (disjoint
    stage columns; an approved cell chains its own approval), so the change is the
    general one — correct-by-construction for any multi-rule cell, single-rule cells
    byte-identical (the 223 prior tests confirm no drift). Approval re-apply keeps its
    own chain step; unifying it is out of scope. 3 tests added. `pytest` (226) +
    `pre-commit` + determinism guard pass. Decision recorded in BACKLOG item 6.
  - **Item 4 — live upload→review→re-run surface: done** (merged, PR #22).
    Branch `feat/upload-review-surface`; spec
    `specs/feat-upload-review-surface.md` + 6 steps committed. A thin web transport
    over `pipeline.run` + `review.ReviewQueue` — no business logic, no new deps
    (stdlib `http.server`), offline. New top-level `webapp/` package outside
    `carbonara/` (multipart parser, `Session`, pure panel renderers reusing the
    now-public `view.CSS` palette, and a pure `handle(…, now=…)` router); the full
    loop is upload → drift gate + one-click mapping confirm → review queue
    (approve/reject) → re-run rendering the footprint with the corrected cell's
    chained lineage. `scripts/serve.py` binds `127.0.0.1` and owns the socket/clock;
    the router reads no clock (timestamp injected at the boundary). Tests drive the
    pure router offline (238 pytest). `/simplify` run and applied. Two deferrals
    (spec): cross-restart persistence + auth/multi-user, and hand-editing the
    mapping.
  - **Item 10 — unify the approval re-apply into `apply_lineage`: done** (merged,
    PR #23). Branch `refacto/unify-approval-lineage`; the BACKLOG
    item-10 entry is the spec. `apply_approvals` now returns one ordered `events`
    list (seed before approval per cell) + `resolved_cells`, dropping `ApprovalChain`,
    the seed/approval split, and the parallel `augment_lineage` loop in `run`; the
    single list feeds both the ledger and `apply_lineage`, whose item-6 chaining
    heads on the seed and chains the approval — the same path any multi-rule cell
    takes. The approved cell's lifecycle, `resolved_cells`, ledger, and drawer are
    unchanged (the approval tier's `data_lineage` `inputs` no longer duplicates the
    resolved `value`, which is not rendered and not in the ledger; decision in
    BACKLOG item 10). `/simplify` self-reviewed (small deletion-heavy diff), clean.
    `pytest` (238) + `pre-commit` + determinism guard pass.
  - **Backlog complete.** All ten BACKLOG items (1–10) are done and merged; the §16
    build and the post-project backlog are both finished. End-to-end verified on the
    merged `main`: `pytest` 238 pass, `scripts/demo.py` runs upload→…→footprint
    (77.3 kgCO₂e), `scripts/build_view.py` renders, and the live `scripts/serve.py`
    surface drives the full upload→review→re-run loop. No open backlog work.

_Update after every PR and merge (rule above): phase or backlog item, branch, open PR, next step._
