# Phase 6 — DuckDB DAG + icanexplain on two vintages *(stretch)*

Branch `phase-6-lea-and-icanexplain`. Implements milestone M6 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, per §6 (two vintages / planted
ground truth), §9 (footprint decomposition), and §11 (library boundaries).
Gated on Phase 5 landing (merged, PR #6).

## Objective

Explain how the catalog footprint changed between two BOM vintages, and prove the
explanation is trustworthy. A deterministic generator emits a controlled **v2
(2025)** vintage that differs from **v1 (2024)** only in planted ways; a tiny
staging→core→mart DuckDB SQL DAG rolls the pipeline's per-line footprints up to a
production-weighted catalog total by material and vintage; icanexplain decomposes
the v1→v2 delta of that total into **volume**, **mix**, and **intensity/factor**
effects. Two checks close it, at two strengths: the contributions **reconcile**
to the observed delta exactly (residual < 1e-6), and they **validate** against
the generator's planted ground-truth decomposition **in direction** — the same
sign on every effect. The pipeline runs on filled weights, so its magnitudes
carry propagated fill error (~10%) against the ground truth; that gap is reported
as QA, not asserted within a tight tolerance. Deterministic end to end — a re-run
reproduces the vintage files, the mart, and the decomposition byte-for-byte.

## The metric being decomposed (§6, §9)

Today's footprint is per component line, `weight_kg × factor(material)`, and the
catalog total sums those lines — **quantity does not enter it**. A "volume"
effect only exists once production volume does, so the decomposition runs over a
distinct **production-weighted catalog total**:

```text
F(vintage) = Σ_line  quantity × (component_weight_g / 1000 × factor_kgco2e_per_kg(material))
```

This is a new mart-level aggregate, not a change to the Phase-5 per-line footprint
or any number the view already shows. It is the sum, over component lines, of the
pipeline's existing `estimated_kgco2e` scaled by the canonical `quantity` column —
no new connector logic.

Decomposed over the material dimension, `F` moves for three reasons between
vintages:

| Effect | What moves | Planted source in v2 |
|---|---|---|
| **Volume** | total production quantity, mix held | a fixed quantity multiplier |
| **Mix** | material composition of that quantity, volume held | a named material-mix shift |
| **Intensity / factor** | kgCO₂e per kg per material | the `material_factors_v2.csv` bump (Phase 5, a labeled hypothetical) |

## The second vintage (§6)

v2 is a **deterministic transform of v1's clean skeleton**, not an independent
re-seed: only then are the true volume/mix/intensity contributions known exactly,
which the exit gate requires (a re-seed entangles every effect with fresh draw
noise and leaves nothing exact to validate against). The generator
(`fixtures/generate.py`, outside `carbonara/` on purpose — it uses seeded
randomness) gains a `vintage` parameter. v2 starts from the same clean rows as v1
and applies three fixed, recorded deltas:

1. **Volume** — a fixed per-archetype quantity multiplier (e.g. hoodies up,
   dresses down).
2. **Mix** — convert a named, fixed set of component lines from one material to
   another (a block of cotton t-shirt bodies → organic cotton).
3. **Vintage stamp** — `year → 2025` on `order_date`, same month/day.

**Plant first, transform second.** The messy cases are planted on the
*untransformed* rows; volume and mix are applied only afterwards. The year stamp
is the sole pre-plant difference, and it feeds no plant's predicate, so the rng
sequence — and thus the corruption layout — is identical across vintages. Both
vintages therefore blank and fill the *same* cells, so the per-vintage fill error
cancels in the v1→v2 delta rather than compounding (an earlier transform-then-plant
order left the two vintages corrupting ~70% different cells, which inflated the
delta's error to ~24%; this ordering cuts it to ~10%, the honest fill-accuracy
floor). Because v2 is a closed-form transform of v1, the true `F(v1)`, `F(v2)` and
each effect's contribution are known exactly and written to a ground-truth
decomposition table.

Generator outputs (all byte-reproducible at the fixed seed):

| File | Contents |
|---|---|
| `fixtures/bom_v2.csv` | the v2 raw vendor file (same messy shape as v1) |
| `fixtures/ground_truth_v2.csv` | true value of every corrupted/blanked v2 cell |
| `fixtures/decomposition_truth.csv` | the known-true production-weighted basis per vintage × material (`mass_kg`, `factor`, `footprint`), over the pipeline's costed universe — fed to the same decomposition to validate the pipeline's |

## Architecture — analytics layer downstream of the connector (§11)

The carbonara pipeline stays the trustworthy deterministic core; the new work is
a thin analytics layer **outside** the package (`analytics/`), consuming the
pipeline's output. This keeps the DAG and icanexplain off the connector's guaranteed
data path, carries their heavier dependencies outside it, and respects §11's "no
wrapper, no DSL, no warehouse" boundary — the DAG never reimplements connector logic,
it aggregates already-augmented rows.

```text
carbonara.pipeline.run(v1) ─┐
carbonara.pipeline.run(v2) ─┴─► raw (per-line footprint + mass, per vintage, in DuckDB)
                                   │  DuckDB SQL DAG
                                   ├─ staging: typed/selected lines
                                   ├─ core:    costed per-line grain
                                   └─ mart:    F by material × vintage  (production-weighted)
                                                 │
                                                 ├─ icanexplain: decompose ΔF → volume / mix / intensity
                                                 ├─ reconcile:   Σ contributions ≈ observed ΔF (tolerance)
                                                 └─ validate:    contributions ≈ decomposition_truth (tolerance)
```

Determinism holds throughout: DuckDB SQL over fixed input and ibis/pandas math are
deterministic; no wall-clock, no unseeded randomness, no network at runtime. The
determinism guard scopes to `carbonara/`; `analytics/` is held to the same bar by
`carbonara-correctness` and a byte-identical-rerun test.

## Dependencies (§2 portability, §11)

Pin in `uv.lock` under an `analytics` dependency group (kept out of the
connector's runtime deps), offline at runtime:

- **icanexplain** — the one footprint decomposition. Pulls `ibis-framework`,
  `pyarrow` and `altair`; we consume its numeric decomposition, not its charts,
  and run ibis on its **pandas** backend (its duckdb backend pins `duckdb<1.2`,
  using the removed `duckdb.functional`, while the connector runs duckdb 1.5+).

**Lea is not adopted.** The dependency-resolution checkpoint flagged here found
the real Lea (`lea-cli`, carbonfact) cannot be used: it requires `sqlglot>=30.2`
while icanexplain's `ibis 9.5` requires `sqlglot<25.21` — an unresolvable
conflict — and it pulls a `google-cloud-bigquery` / `gitpython` / `rsa` tree
disproportionate to "a tiny DuckDB DAG". (The PyPI `lea` 4.x is an unrelated
probability library.) The staging→core→mart DAG is therefore **plain DuckDB
SQL** — `.sql` models run in dependency order by a small runner, which honors
§11's "no wrapper, no DSL, no warehouse" boundary directly and keeps the
analytics-engineering layering. Declining a conflicting heavy dependency is the
library judgment §11 rewards ("using few libraries well, not all of them").

## The PR-writing skill (build harness)

Add `.claude/skills/carbonara-pr/` — PR *structure and process* (the article
referenced for this phase), complementing `carbonara-voice` (which governs the
*wording*). Adopts: a clear title + a description that states what/why and how it
was tested, self-explanatory code, test-before-push, house coding standards, and
tagging the right reviewer. Explicitly **out of scope for this project**, with the
reason recorded in the skill: splitting into small/atomic PRs (the workflow is one
PR per phase; atomicity lives at the commit), and multi-reviewer feedback
etiquette (a single maintainer merges). Add a row to the CLAUDE.md harness table.

## Deliberately out of scope

- **Factor uncertainty in the decomposition** — the intensity effect uses the
  point factors; the decomposition carries no confidence interval (consistent
  with Phase 5).
- **Composition-weighted factors** — a component is still costed by its single
  normalized material (§9).
- **Cross-dimension (category/country) decomposition** — the metric is decomposed
  over material only; other dimensions are a later extension.
- **A second provenance subsystem or a scheduler/warehouse for the DAG** — the DAG is
  a handful of SQL models run once over a local DuckDB file.
- **Surfacing the explanation in the brand-facing view** — the Phase-6 deliverable
  is the reconciled metric + explanation as a repeatable artifact; wiring it into
  the Phase-5 view is not in this gate.

## Ordered steps (one commit each)

1. **Spec** — this file, and mark Phase 5 merged (PR #6) in the CLAUDE.md Current
   status.
2. **PR-writing skill.** `.claude/skills/carbonara-pr/SKILL.md` (per above) + the
   CLAUDE.md harness-table row.
3. **Second vintage.** Extend `fixtures/generate.py` with a `vintage` parameter and
   the v2 transform (per-archetype volume multiplier, named material-mix shift,
   2025 stamp); write `bom_v2.csv`, `ground_truth_v2.csv`, and
   `decomposition_truth.csv`. Tests: regenerate twice byte-identical; the planted
   contributions sum to the true delta; v2 preserves the messy-case structure.
4. **Deps + staging.** Pin `icanexplain` in an `analytics` group in `pyproject.toml` /
   `uv.lock` (resolve with `duckdb` offline; Lea is not adopted, see above). `analytics/` package: run both vintages through
   `carbonara.pipeline.run`, load per-line footprint + quantity into DuckDB as the
   staging tables. Test: deterministic load, expected row counts per vintage.
5. **SQL mart.** staging→core→mart DuckDB SQL models + a tiny runner; mart = `F`
   by material × vintage. Test: the mart equals a pure-Python reference aggregate
   of the same rows; identical across runs.
6. **icanexplain decomposition.** Decompose ΔF over material into volume / mix /
   intensity; build a reconciliation record (Σ contributions vs observed ΔF within
   tolerance). Tests: reconciliation holds; decomposition is reproducible.
7. **Ground-truth validation + demo entry.** Assert the decomposition agrees with
   `decomposition_truth.csv` in direction on every effect (the magnitude gap is
   propagated fill error, reported as QA); `scripts/build_explanation.py` writes
   the reconciled explanation artifact. Tests: sign agreement per effect.
8. **Exit-gate capstone + docs.** End-to-end test: generate v2 → run both vintages
   → SQL mart → icanexplain decomposition → reconcile to observed ΔF → validate
   against planted ground truth, all byte-reproducible. Update the README (doctest)
   and the CLAUDE.md Current status.

## Exit gate (brief §16)

- A repeatable production-weighted metric `F(vintage)` and a reconciled
  explanation of ΔF whose volume / mix / intensity contributions **sum to the
  observed delta** exactly (residual < 1e-6).
- The contributions **validate against the planted ground-truth decomposition**
  (`decomposition_truth.csv`) **in direction** — the same sign on every effect;
  the ~10% magnitude gap is propagated fill error, reported as QA.
- v2 is generated deterministically; the vintage files, the mart, and the
  decomposition reproduce byte-for-byte on a re-run.
- The DAG is a tiny layered SQL transformation over the connector's output, not a
  reimplementation of it (§11); the DAG and icanexplain live outside `carbonara/`.
- `uv run pytest` and `uv run pre-commit run --all-files` are green.
