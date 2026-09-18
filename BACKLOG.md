# Future work

An ordered backlog of improvements and known limits found in a full read of the
shipped connector (ingest → normalize → fill → footprint → view, plus the
`analytics/` decomposition). Each item names what to change, why, where in the
code, and whether it touches the deterministic data path. The
[PROJECT-BRIEF.md](PROJECT-BRIEF.md) is the design of record; this file is the
list of things worth doing next, not a redesign.

## Build order

Ordered by dependency and payoff. Items 1–3 make the connector credible on real
files; item 4 is the largest and most visible; 5–6 are independent cleanups that
can land any time.

| # | Item | Size | Data path? | Depends on |
|---|---|---|---|---|
| 1 | Lift `category` into the contract | small | yes | — |
| 2 | Parse XLSX, not just detect it | medium | yes (ingest) | — |
| 3 | Run one real, messy source file end to end | small | no (exercise) | 1, 2 |
| 4 | A live upload → review → re-run surface | large | no (wraps `run`) | — |
| 5 | Replace icanexplain with the closed-form split | medium | no (`analytics/`) | — |
| 6 | Use the augment lifecycle in the live pipeline | medium | yes | — |
| 7 | Parse semicolon-delimited (European) CSVs | small | yes (ingest) | — |
| 8 | Material synonym/alias table | small | yes | — |
| 9 | Expand the factor table (wool, acrylic) | small | yes (data) | — |
| 10 | Unify the approval re-apply into `apply_lineage` | medium | yes | 6 |
| 11 | Review-console UX: default-approve + horizontal readiness | small | no (transport/view) | 4 |
| 12 | Reuse-first simplification pass | small | yes (byte-identical) | — |

Items 1, 2, 4, 5 are independent of each other and can be parallelized. Item 3
is the validation step for 1 and 2 and should follow them. Item 6 retires a
known corner-cut and can land whenever. Items 7 and 8 were surfaced by item 3's
real-file search and let the full pipeline run on real, licensed apparel data;
item 9 would cost more of it. Item 10 is a cleanup that item 6 unlocked — it
depends on 6 and can land whenever after it. Item 12 is an independent craft
cleanup that can land any time.

## Capability gaps

### 1. Lift `category` into the contract

`category` is derived by string-splitting the style id (`style_id.split("-")[0]`
in `fill.py:42` and `footprint.py:116`, duplicated). The whole fill-ladder
back-off pivots on it (`fill.py:50`). This convention is planted by the fixture
generator; a real brand export will not encode category in the style id, so the
back-off would silently degrade to one level. Add `category` as an explicit
`CanonicalRecord` field, resolve it once during materialize, and delete both
`_category` helpers. Deterministic — the value moves from a string convention to
a named cell with its own lineage.

**Done** (`feat/category-in-contract`). `category` is a required `str` on
`CanonicalRecord`, resolved once in `materialize` via `derive_category(style_id)`
— treated as an identity-derived projection like `record_id` (a deterministic
function of an identity field, not an imputed value), so it carries no separate
Bloodline source or ledger event; its "own lineage" is being a first-class named
cell in the canonical frame, traceable beside the `style_id` it comes from. Both
`_category` helpers are gone; `fill` and `footprint` read `record.category`. This
leaves the real-file gap the item names — a brand export that does not encode the
archetype in the style id — for item 3's exercise to expose, since the derivation
still assumes the fixture convention.

### 2. Parse XLSX, not just detect it

Ingest detects XLSX by ZIP magic bytes (`ingest.py:86`) and then raises
`UnsupportedFormatError` (`ingest.py:158`); only CSV is parsed. Real BOMs and
catalogs are frequently Excel. Add an XLSX reader (pandas already ships
`read_excel`; `openpyxl` would be the one new pinned dependency) behind the same
profile/schema-drift gate, so an XLSX file follows the identical path a CSV does.
Data path — must stay deterministic (fixed sheet selection, no locale-dependent
parsing).

**Done** (`feat/parse-xlsx`). `ingest._read_xlsx` reads the first sheet with
`openpyxl` directly and converts each cell to a string (`_cell_str`), rather than
`pandas.read_excel`. Decision: `read_excel` renders a native Excel **date** cell
as `"2024-01-08 00:00:00"` (not the ISO `order_date` the CSV path carries) and
leaves number/blank handling to pandas' type inference; reading cells directly
gives a faithful, locale-free conversion (integers without a trailing `.0`, date
cells to ISO, blanks to `""`) — the determinism the item requires. `openpyxl` is
the one new connector dependency, and pandas is a transitive user of it anyway.
`read_source`/`read_rows` are the shared format-agnostic readers (a caller feeds
either format to `pipeline.run` identically); `admit` dispatches on the detected
format and a malformed XLSX raises a clear `UnsupportedFormatError`. The demo
scripts still read the CSV fixture with `csv.DictReader` (unchanged); routing them
through `read_rows` is left out of scope to avoid touching their output.

### 3. Run one real, messy source file end to end

Every input today is synthetic. That is the right call for the fill-accuracy
metric — only planted ground truth makes measured error possible — but it means
the connector has never met a file it did not generate. Take one genuinely ugly
public file (e.g. a government textile-import CSV: quoted fields with commas,
blank or multi-part headers) and run it through ingest → normalize, with no
footprint claim, purely to prove the drift gate and normalizers survive real
mess. Keep it out of the QA suite (no ground truth); it is an exercise, not a
determinism fixture.

**Done** (`feat/real-file-exercise`). The file is a real U.S. textile-import table
(`samples/us_textile_imports_by_fiber.csv`, USDA ERS from Census/Commerce trade
data — a quoted field with an embedded comma), run by
`scripts/real_file_exercise.py`. It lives in `scripts/`/`samples/`, so pytest never
collects it — out of the QA suite, as required. Findings: ingest parses the
quoted-comma CSV; the drift gate returns `review_required` with no mapping (no
column matches the BOM contract), so a real non-BOM file is stopped, not processed;
`resolve_material` resolves `Cotton → cotton` and flags `Wool`/`Silk`/`Linen`/
`Synthetic` (not in the vocabulary) instead of guessing; `parse_date` nulls the
year-only periods — no crashes. Decision: the file is aggregate statistics with no
per-item weights/suppliers/SKUs, so the exercise proves the **drift gate + field
normalizers** survive real mess but does not exercise the full fill→footprint path —
the gate is the safety net that stops exactly this. Chosen file is USDA ERS
(published from Census data) because the strict-Census OTEXA tables are not served
as a direct CSV.

A follow-up search for a real apparel file with per-item **material and weight**
found that such data exists and is openly licensed but is blocked by format, not
availability (recorded in `samples/README.md`): a Shopify brand-catalog export is
product-level with material only in free text (`materialize` names the missing
`material`), and NPCGA — 16 464 Norwegian post-consumer garments (Zenodo
`10.5281/zenodo.20440761`, CC BY-SA 4.0) — carries real fibre composition, grams,
brand, and country but is **semicolon-delimited**, which the connector's comma-only
reader cannot parse. A `;`-delimited (European) CSV reader is the natural next item
that would let the full pipeline run on real, licensed apparel data.

### 4. A live upload → review → re-run surface

The brief describes "a thin, clean full-stack surface"; the shipped artifact is a
static HTML render (`view.py`, `scripts/build_view.py`) plus a CLI walkthrough
(`scripts/demo.py`). A small web surface — file upload, the drift-gate decision,
the review queue with approve/reject, and a re-run that shows the chained cell
lineage — would make the interactive loop real instead of narrated. It can be a
thin wrapper over `pipeline.run` and `review.ReviewQueue` (both already return
everything the page needs), so the connector stays the single source of truth and
the surface holds no business logic. Not in the data path; keep the determinism
in `run`, not the transport.

**Done** (merged, PR #22, `feat/upload-review-surface`). Decisions: stdlib `http.server`
(`ThreadingHTTPServer`, server-rendered HTML, plain form POSTs) — zero new
dependencies, offline; the transport lives in a new top-level `webapp/` package
outside `carbonara/` (like `analytics/`), so the determinism guard's domain stays
the connector alone; the slate-dashboard palette (`view.py`) is reused. Scope is
the full loop (upload → drift gate + one-click mapping confirm → review queue →
re-run with chained lineage); cross-restart persistence, auth/multi-user, and
hand-editing the mapping are deferred. The `handle()` router reads no clock; the
timestamp is injected at the I/O boundary (`serve.py` passes wall-clock per
request, tests pass a fixed constant). **Deviation:** this item has a spec file
(`specs/feat-upload-review-surface.md`) rather than only this entry — at the user's
request, since item 4 is the largest backlog item.

### 7. Parse semicolon-delimited (European) CSVs

`ingest._read_csv` reads with `csv.DictReader`'s default comma delimiter, so a
semicolon-delimited file — the European convention, where the comma is the decimal
separator — is read as a single column and the drift gate flags the whole schema.
Item 3's search found a real, openly-licensed apparel dataset in exactly this shape
(NPCGA — 16 464 Norwegian post-consumer garments, [Zenodo
10.5281/zenodo.20440761](https://doi.org/10.5281/zenodo.20440761), CC BY-SA 4.0)
with real fibre composition, weight in grams, brand, and country — unreadable only
because of the delimiter. Detect the delimiter from the header (comma vs semicolon,
whichever the header uses) and parse accordingly; keep it deterministic (a fixed
header-count rule, no locale sniffing) and leave every comma file unchanged. Data
path — the same `_read_csv` that feeds the drift gate and `read_rows`.

### 8. Material synonym/alias table

The material vocabulary (`references/materials_v1.csv`) resolves a value by exact
canonical match or shorthand code (`CO`, `PL`), then a bounded fuzzy proposal — but
it has no full-word **synonym** map, so a real fibre label like `polyamide` (the
ISO/European name for `nylon`) resolves to nothing and its footprint is flagged
unmapped (seen on the NPCGA data in item 7). Add a versioned synonym column to the
vocabulary so citable one-name-to-another equivalences (`polyamide → nylon`, and
the common fibre codes) resolve deterministically as exact reference lookups — not
as guesses, and never for an ambiguous label. Deliberately **out of scope**: a
disjunctive label like `"polyamide or nylon"` stays a review proposal (the reviewer
decides, not the vocabulary); a fibre with no factor at all (`wool`, `silk`,
`acrylic`) needs a factor added to the factor table, which is a separate,
larger reference-expansion item, not a synonym.

### 9. Expand the factor table (wool, acrylic)

Item 7's NPCGA run flags common fibres the factor table does not carry — `wool`,
`acrylic`, `silk` — as unmapped (no factor), so they are not costed. Ecobalyse's
textile library **does** have `Laine par défaut` (wool) and `Acrylique` (acrylic),
so add them the exact, cited way: their material ids to `scripts/fetch_factors.py`
and a token-gated re-fetch that writes `references/material_factors_v1.csv`. Not a
plain edit — every factor is an exact Ecobalyse `cch` value, never a guessed number
(brief §9), so it needs the `ECOBALYSE_TOKEN` and a check that the existing eight
values are unchanged (they are pinned by the footprint tests and the demo total).
`silk` is **not** in Ecobalyse's textile library, so it stays unmapped until a
citable factor from a comparable source is found — do not invent one. Once the
factors land, add the fibres to the vocabulary (item 8) so they resolve.

**Done** (`feat/semicolon-csv-reader`). `fetch_factors.py` gained the Ecobalyse
aliases `ei-laine-par-defaut` (wool) and `ei-acrylique` (acrylic); a token-gated
re-fetch wrote `wool` (28.9041) and `acrylic` (11.0771) into
`material_factors_v1.csv` (and the same values into v2, which revises only
polyester) — the pinned eight came back byte-identical, so nothing shifted. Both
were added to `materials_v1.csv`, so the NPCGA run now costs them: 116 of 200
garments, 157.2 kgCO₂e, with `wool` the second-largest material despite six
garments (its factor is ~5× cotton). `silk` was **not** invented — it stays
unmapped.

### 5. Replace icanexplain with the closed-form split

The v1→v2 decomposition pulls `icanexplain` and `ibis`, and then pins ibis's
pandas backend to avoid a duckdb version conflict its duckdb backend forces
(`explain.py:71`). The reconciliation it produces holds *by construction*, so the
library earns little. The closed form is already written and tested:
`intensity_from_factor_change` is `mass_from × (factor_to − factor_from)`
(`explain.py:55`). Compute both effects directly from the mart, drop
`icanexplain` and `ibis` from the `analytics` group, and remove the backend pin.
Keep the DuckDB staging→core→mart DAG (`analytics/dag/*.sql`) — the SQL modeling
is worth showing; the decomposition library is not.

**Done** (`refacto/closed-form-split`). `analytics/explain.decompose` computes both
effects directly from the mart — `intensity = mass_from × (factor_to − factor_from)`
per material (i.e. `intensity_from_factor_change` summed over materials), volume/mix
the remainder of each material's footprint delta — so reconciliation holds by
arithmetic and the intensity total sits on the planted polyester bump exactly, as
under icanexplain. `icanexplain` and its `ibis` stack are gone, and the pandas
backend pin with them. Decision: the whole `analytics` dependency **group was
removed**, not only `icanexplain` — `pyarrow`/`pyarrow-hotfix` were there only for
the ibis arrow bridge, so once the library is gone the layer needs nothing beyond
the connector's own pandas + duckdb (the 17 analytics tests pass with those deps
uninstalled). The DuckDB staging→core→mart DAG (`analytics/dag/*.sql`) is unchanged.

## Root-cause items and known limits

### 6. Use the augment lifecycle in the live pipeline

`carbonara/augment.py` keeps a cell's ordered rule lifecycle inline, but the live
fill/normalize passes still write a single source and clobber with `override=True`
(one rule per cell today). Only the Phase-8 approval re-apply uses the chained
form. Where a cell is legitimately touched by more than one rule, route it through
`augment_lineage` instead of clobbering, so the spine carries the full history and
matches the ledger. Data path — additive and deterministic, but re-check the
determinism guard and the lineage reproducibility tests.

**Done** (`feat/augment-in-pipeline`). Fixed the mechanism rather than one call site:
`apply_lineage` (the shared spine) now writes a cell's first rule as a plain head
Source, then chains any further rule on that cell through `augment_lineage` (oldest
first), so the lifecycle matches the ledger instead of the last write clobbering it.
Scope decision: there is **no live cell touched by more than one rule today** — the
stage columns are disjoint (normalize per column, fill only the null weights,
footprint only `estimated_kgco2e`), and an approved cell carries only its seed event
in the clobbering pass (its approval already chains). So the honest change is the
general one — `apply_lineage` is correct-by-construction for any multi-rule cell,
and a single-rule cell is byte-identical to the plain write (the 223 existing tests
confirm no drift). The Phase-8 approval re-apply keeps its own chain step; unifying
it into `apply_lineage` is a deeper refactor left out of scope. Three tests added
(`tests/test_lineage.py`) prove a two-rule cell chains through `apply_lineage`, a
single-rule cell keeps a plain head, and the chaining is reproducible; the
determinism guard passes.

### 10. Unify the approval re-apply into `apply_lineage`

Item 6 made `apply_lineage` chain a cell's later rules, so the Phase-8 approval
re-apply no longer needs its own parallel mechanism. Today `pipeline.run` keeps the
approval events out of `lineage_events` and attaches their lineage through a
separate `augment_lineage` loop, and `apply_review` splits each correction into a
`seed_event` (fed to `apply_lineage`) and an `approval_event` (ledger only, chained
after) — a special case that predates the general chaining. Route both events
through `apply_lineage` like any other rule so its own chaining produces the same
`normalize_material → reference_resolve` lifecycle, then drop the separate loop and
collapse the seed/approval split in `ApplyResult`. One spine carries every cell's
lifecycle. Data path — must stay byte-identical for the approved cell's lifecycle
and reproduce the current `resolved_cells` and provenance drawer; re-check the
determinism guard and the review-loop tests. A genuine simplification (removes a
special case), not urgent — the current dual path works and is tested.

**Done** (merged, PR #23, `refacto/unify-approval-lineage`). `apply_approvals` now returns one
ordered `events` list (each corrected cell's normalize seed before its approval)
plus `resolved_cells`; `ApprovalChain`, the `seed_events`/`approval_events` split,
and the parallel `augment_lineage` loop in `pipeline.run` are gone. `run` feeds a
single event list to both the ledger and `apply_lineage`, whose item-6 chaining
writes the seed as the head Source and chains the approval — the same path any
multi-rule cell takes — so the `normalize_material → reference_resolve` lifecycle,
`resolved_cells`, the ledger, and the rendered drawer are unchanged (the pipeline,
view, and review-loop tests confirm it). One deliberate behavior note: the approval
tier's `data_lineage` `inputs` no longer duplicates the resolved `value` (the cell
already holds it, and the drawer renders only `source_type`/`rule_id`); the ledger
row's `method_params` are unchanged. Determinism guard passes; `pytest` (238) +
`pre-commit` clean.

### 11. Review-console UX: default-approve + horizontal readiness

Two refinements to the item-4 review console (transport/view only, not the data
path), from using it on the fixture BOM:

1. **Default the review queue to all-approved.** Approving every finding one at a
   time is tedious. On confirm, default every finding to *approved* (a "select
   all" default) and let the reviewer *reject* the ones they don't want; keep both
   the approve and reject controls on every row, with the current choice marked.
   The re-run applies whatever is still approved — actionable findings (a mapping
   with a `proposed_value`) mint a correction, the rest are a no-op status. The
   reviewer still triggers the re-run explicitly, and can reject any row, so this
   is a UI default, not a silent edit; the default approvals carry a `note` so the
   ledger distinguishes a bulk default from an explicit click. Changes
   `webapp/render.py` (always render both buttons, mark the active one) and
   `webapp/app.py` (`_confirm` bulk-approves).
2. **Lay the Readiness panel out horizontally.** In `carbonara/view.py` the
   Readiness panel is the narrow left column of a two-column grid, so its stacked
   metrics look squished. Make Readiness a full-width band at the top with its
   metrics in a horizontal row, and the review queue full-width below. Presentation
   only — the content (headline, split, coverage, findings-by-severity) is
   unchanged, so the `test_view.py` content assertions still hold.

**Done** (merged, PR #24, `feat/console-ux-fixes`). Both fixes shipped. (1) On
confirm the console defaults every finding to approved (`webapp/app.py`), both
controls stay on every row with the active one marked (`webapp/render.py`); default
approvals carry a `note` marking a bulk default. Loop tests updated for the new
default (confirm pre-approves → the mapping costs on re-run; rejecting all the
reusable-alias findings leaves it uncosted). (2) `carbonara/view.py`'s readiness is
now a full-width horizontal band; `test_view.py` content assertions hold. Verified
live in the browser. `pytest` (238) + `pre-commit` pass.

### 12. Reuse-first simplification pass

Four behavior-preserving cleanups found in a craft review (the reuse-first
ladder, `carbonara-craft`). Output is byte-identical, so the existing tests pin
each one:

- `normalize.py` — `resolve_supplier` and `resolve_material` share the same
  "best fuzzy match" block; extract one `_best_match(raw, candidates)` helper.
  The `max(scored, key=lambda pair: (pair[0], pair[1]))` key is redundant —
  `scored` is a list of `(ratio, name)` tuples and `max` already orders by ratio
  then name — so it collapses to a plain `max(...)`, keeping the deterministic
  tie-break.
- `footprint.py` — the hand-rolled `{s: 0 for s in FootprintStatus}` plus
  increment loop in `summarize` is `collections.Counter` (which reads 0 for an
  absent status).
- `view.py` — the four `cells = []; cells.append(...); "".join(cells)`
  row-builders become `"".join(f"..." for ...)` comprehensions, matching the
  style already in `webapp/render.py`.
- `view.py` — the three `sum(1 for ... severity ...)` passes in `render_view`
  are one `Counter` over the findings' severities.

Data path (`normalize.py`, `footprint.py`) — must stay byte-identical; the
determinism guard and the existing tests are the proof. **Out of scope:**
table-driving the six normalize parse→event blocks. It is real repetition, but
the flat blocks keep each rule's `rule_id`/`source_type`/renderer visible inline,
which is worth more than the line count in a provenance-critical file.

### The five-tier ladder is two active tiers for weight

The fill ladder is documented as five tiers, but a missing weight only ever
enters at tier 3 (grouped median) → tier 4 (reference constant) → tier 5 (leave
null); tiers 1–2 have no applicable input for a weight gap and the formula tier
lives in the footprint instead. This is stated honestly in `fill.py:1`, and is
correct scoping, not a defect — noted here so the ladder's shape is not mistaken
for five live weight paths.

## Non-goals (unchanged)

These are settled design boundaries, restated so the backlog is not misread as an
invitation to cross them.

- **No LLM in the data path.** Frontier AI is a build-time tool for writing and
  refactoring the code (agentic engineering); it is never a runtime dependency of
  the connector. A value produced by a model is not reproducible or auditable, so
  it does not belong in ingest, normalize, fill, or footprint. This holds even
  for build-time convenience — reference vocabularies and aliases stay
  hand-versioned CSVs, not model output.
- **No warehouse, no cross-file ETL.** One file at a time, in memory. The scale
  question — many files across many sources over time — is deliberately out of
  scope; the append-only ledger and content-hash idempotency are what a later
  warehouse would build on, not something to build here.
- **No method-selecting imputation.** The fill rule is fixed and its error is
  measured (QA), never tuned or auto-selected against the held-out truth.
