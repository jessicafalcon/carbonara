# Phase 5 — Footprint + brand-facing view + provenance drawer

Branch `phase-5-footprint-and-view`. Implements milestone M5 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, per §9 (footprint) and §10 (the view).

## Objective

Compute a component-level carbon footprint from the filled BOM, and render one
brand-facing view that lets a reviewer trace any displayed number back to the
source row, the rules applied, and the factor version used. The footprint is the
project's central `DERIVED_FORMULA` case — the tier-1 formula mechanism deferred
from Phase 4 — and is wired with a ledger event and a Bloodline source like every
other rule. Deterministic throughout: a re-run reproduces the footprint, the
ledger, the lineage, and the rendered HTML byte-for-byte.

## The footprint formula (§9)

```text
estimated_kgco2e(component) = component_weight_g / 1000 × factor_kgco2e_per_kg(material)
```

Per component line, `material` is `material_normalized` (a resolved vocabulary
hit) and the factor comes from the versioned Ecobalyse/ADEME table. The estimate
is a **derived value**, so each one emits a `DERIVED_FORMULA` `RuleEvent` on the
`estimated_kgco2e` column and a matching Bloodline source — the same dual-store
provenance every fill and normalization already writes (§7.1, §8).

Each footprint value carries, per §9:

- **factor source + version** — from the factor table row (method params).
- **material-mapping confidence** — `1.0` for an exact vocabulary hit. A component
  whose material never resolved (the `Organic cottn` proposal was surfaced, not
  applied — Phase 3) has **no factor**: it is left unmapped and flagged, never
  silently costed at zero. This is the observed mapping gap the coverage panel
  reports.
- **aggregation rule** — only `COSTED` rows feed the headline totals. A row with
  no factor (`UNMAPPED`) and a row whose weight tripped the plausibility band
  (`FLAGGED` — the weight is still derived, but not trusted enough to sum) are
  both reported as coverage instead, so a filled-then-flagged input never hides
  inside a total (`carbonara/footprint.py`).
- **observed-vs-filled input share** — whether the `component_weight_g` behind the
  estimate was observed (normalized from the source) or filled by the ladder
  (grouped median / reference constant). Read from the fill events, not guessed.
- **uncertainty range** — the weight's range propagated through the factor:
  `[low_g/1000 × factor, high_g/1000 × factor]`. An observed weight has a point
  estimate (no range). Factor uncertainty is out of scope (below).

Estimates aggregate to product (`style_id`) and catalog, carrying the coverage
and uncertainty labels up with them.

## Material emission factors (§5, §9)

`references/material_factors_v1.csv` — one row per material, one citation per row:

```text
material, factor_kgco2e_per_kg, source, source_version, source_ref
```

Values are the climate-change indicator (kgCO₂e per kg of material), pinned as a
versioned in-repo snapshot so the data path stays offline and reproducible. The
snapshot is fetched at author time by `scripts/fetch_factors.py` (a build-time
script outside the connector package): the per-indicator `cch` value is
token-gated behind an Ecoinvent 3.9.1 license, so the script reads a secret token
from a gitignored `.env` and derives each fibre's factor from the Ecobalyse
simulator — 1 kg of the single material with every life-cycle step disabled
except the material stage. Where a component material has no Ecobalyse entry
(fixture hardware — `brass`, `metal`), the row cites a representative ADEME value
explicitly. Loaded by `material_factors()` + a `MaterialFactor` record in
`carbonara/references.py`, alongside the existing `reference_weights()` loader.

The factor table is a labeled assumption set (§15): the footprint is an estimate
with stated factor provenance, never claimed precise where it rests on filled
weights.

## Factor revision → recompute + version diff (§12)

The footprint is parameterized by factor version. A revision ships as
`references/material_factors_v2.csv` (a hypothetical polyester revision, cited as
such — Ecobalyse serves one live snapshot). Recomputing under v2:

- writes **new** `DERIVED_FORMULA` events under a new `run_id` — the ledger is
  append-only, so the v1 events are untouched (no history corruption). The run id
  is keyed to a **content hash of the reference data** (`reference_digest`), not
  just the version label, and each footprint event records the factor table's
  `factor_content_hash`; an edit to any factor or vocabulary is therefore a new,
  detectable run (§8.3), never a silent change under a reused id;
- yields a **version diff** (`carbonara/footprint.py`): per material / product, the
  v1 estimate, the v2 estimate, the delta, and the factor-version change.

The view surfaces the diff. This is the §12 "factor-table revision → recalculated
metrics + factor-version diff" case, done as a direct version comparison — not a
statistical decomposition (icanexplain is Phase 6, stretch).

**Why v2 is a hypothetical, not a second real release.** A real historical
Ecobalyse factor set is not obtainable through public or token access: the API
serves only the current release (no version parameter, no versioned hosts), and
the detailed climate-change data in Ecobalyse's git history is AES-encrypted with
an internal data key that is separate from the public API token. The exact `cch`
figures we can fetch are therefore current-release only (v1). v2 is a labeled
hypothetical polyester revision, sufficient to exercise the recompute/diff/
append-only mechanism §12 requires. A genuinely real v2 arrives when Ecobalyse
publishes its next release — re-running `scripts/fetch_factors.py` against a fresh
checkout then produces it, and the diff becomes a real revision.

## The pipeline orchestrator

`carbonara/pipeline.py`: one deterministic entry that runs
materialize → normalize → fill → footprint, collecting records, events, and
findings, then building the ledger, the Bloodline-tagged frame, and the
fill-accuracy report. Pure and injected (`run_id`, `created_at` passed in, never
read from the clock), so the view and the demo share one path and a re-run
reproduces everything. Replaces the inline wiring the Phase 4 tests repeat.

`carbonara/accuracy.py` is scoped to the weight column so the footprint's
`DERIVED_FORMULA` events (a different column) are never mistaken for weight fills.

## The view (§10) — Slate dashboard

A **self-contained, deterministic static HTML export** — no server, offline,
a pure function of the pipeline output, snapshot-testable. `carbonara/view.py`
exposes `render_view(model) -> str`; the render reads no clock and no randomness,
so it lives in the connector package under the determinism guard. The page shows
a **run signature** (run id, ruleset version, factor version), not a wall-clock
timestamp, so the HTML is byte-reproducible.

Visual direction (a data/dev tool, not an editorial page — `carbonara-craft`):

| Token | Value |
|---|---|
| Background | slate `#1b2129` |
| Accent | blue-green teal `#20c4a8` |
| Flag / alert | `#f87171` |
| Type | Space Grotesk (headings) + monospace (data), self-hosted or system stack |
| Layout | dense sectioned tables, hairline rules — no card grid, no cream/serif |

Panels (§10):

- **Readiness** — schema-drift status; material / weight / country coverage;
  observed / derived / referenced / imputed shares; anomalies by severity.
- **Review queue** — findings with raw value, proposed rule, confidence.
- **Footprint + material basket** — estimate by material / category, with factor
  version, coverage, and uncertainty labels; the factor v1→v2 diff.
- **Provenance drawer (per number)** — `metric → footprint rows → rules applied →
  source file/row + factor version`, driven by a trace JSON embedded from the
  ledger and the Bloodline spine, toggled by vanilla JS (no fetch, no framework).

A thin `scripts/build_view.py` (outside the connector package) runs the pipeline
over `bom_v1` and writes the HTML to a build path; the rendered artifact is not
committed.

## Deliberately out of scope

- Factor (intensity) uncertainty ranges — only weight uncertainty is propagated;
  the footprint labels the factor version, not a factor confidence interval.
- Composition-weighted (blended) factors — the footprint costs a component by its
  single normalized material, per §9; a blend is not split across factors.
- icanexplain / Lea (Phase 6, stretch): the v1→v2 diff here is a direct value
  comparison, not a volume/mix vs. intensity decomposition.
- An interactive server or SPA — the view is a static export by design
  (determinism, portability, offline).

## Ordered steps (one commit each)

1. **Spec** — this file.
2. **Material factors.** `references/material_factors_v1.csv` (+ README note),
   fetched by the build-time `scripts/fetch_factors.py` (token-gated Ecobalyse
   `cch`), and a `material_factors()` loader with a `MaterialFactor` record in
   `carbonara/references.py`. Tests.
3. **Footprint.** `carbonara/footprint.py`: per-component
   `weight_kg × factor(material)`, emitting `DERIVED_FORMULA` events with factor
   source/version, weight source (observed/filled), mapping confidence, and
   uncertainty; unmapped material flagged; aggregation to product/catalog and the
   observed-vs-filled share. Scope `accuracy.py` to the weight column. Tests
   (doctest of the formula, tier and unmapped cases).
4. **Pipeline orchestrator.** `carbonara/pipeline.py`: deterministic
   materialize → normalize → fill → footprint with injected run context, building
   ledger + lineage frame + accuracy. Tests (reproduces exactly).
5. **Factor revision + diff.** `references/material_factors_v2.csv` and a footprint
   version-diff helper; recompute appends under a new `run_id` with v1 history
   intact. Tests: §12 factor-revision case, no history corruption.
6. **View render.** `carbonara/view.py`: pure `render_view(model) -> str`
   self-contained Slate-dashboard HTML — readiness, review queue, footprint +
   material basket + factor diff, provenance drawer (embedded trace JSON + vanilla
   JS). Structure + determinism tests (byte-identical re-render, trace present).
7. **Demo entry + trace journey.** `scripts/build_view.py` writes the HTML over
   `bom_v1`; a test walks the exit-gate journey — one displayed footprint number →
   its footprint row → the rules applied → the source row + factor version.
8. **§12 exit gate + docs.** End-to-end test: footprint over `bom_v1`, factor
   revision recompute + diff, the trace journey, and a re-run reproducing
   footprint / ledger / lineage / HTML byte-for-byte. Update the README (doctest)
   and CLAUDE.md Current status.

## Exit-gate journey (brief §16)

The reviewer completes one end-to-end trace, confirmed by test and by opening the
rendered view:

1. Read a displayed catalog/product/material footprint number.
2. Expand its provenance drawer → the footprint rows that sum to it.
3. Each row → the rules applied (the `DERIVED_FORMULA` footprint event, plus the
   weight fill or normalization behind the weight) from the ledger.
4. → the source file and row id, and the factor version used.
5. Revise a factor (v1 → v2): metrics recompute, the view shows a factor-version
   diff, and the v1 ledger events remain intact (append-only, no corruption).

## Exit gate

- The footprint computes `weight_kg × factor(material)`, aggregated to
  product/catalog, with factor source/version, mapping confidence, observed-vs-
  filled share, and an uncertainty range.
- The view renders all four panels; a reviewer traces one displayed number to its
  source row and factor version (the journey above).
- A factor-table revision recomputes metrics and shows a version diff without
  corrupting history.
- A re-run reproduces footprint, ledger, lineage, and HTML exactly.
- `uv run pytest` and `uv run pre-commit run --all-files` are green.
