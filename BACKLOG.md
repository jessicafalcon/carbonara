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

Items 1, 2, 4, 5 are independent of each other and can be parallelized. Item 3
is the validation step for 1 and 2 and should follow them. Item 6 retires a
known corner-cut and can land whenever.

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

## Simplifications

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

## Root-cause items and known limits

### 6. Use the augment lifecycle in the live pipeline

`carbonara/augment.py` keeps a cell's ordered rule lifecycle inline, but the live
fill/normalize passes still write a single source and clobber with `override=True`
(one rule per cell today). Only the Phase-8 approval re-apply uses the chained
form. Where a cell is legitimately touched by more than one rule, route it through
`augment_lineage` instead of clobbering, so the spine carries the full history and
matches the ledger. Data path — additive and deterministic, but re-check the
determinism guard and the lineage reproducibility tests.

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
