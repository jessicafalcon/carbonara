# Apparel BOM Connector — Final Proposal

*A lean connector that turns a messy supplier BOM into an auditable, component-level carbon estimate — and can prove where every number came from.*

---

## 1. Product statement

Ingest one messy apparel BOM / catalog / purchase-order file. Detect schema drift, normalize and validate it through explicit versioned rules, fill gaps conservatively through a deterministic hierarchy, compute a clearly-labeled component-level footprint, and let a reviewer trace any number back to the rule that produced it and the source row it came from.

Every value the pipeline touches is the product of one **versioned, deterministic rule** that leaves a record. Nothing is silently corrected, nothing is randomly guessed, and no step depends on an LLM at runtime.

---

## 2. Scope and positioning

The work sits at the **Collect** and **Measure** stages of environmental data: parse heterogeneous BOM/catalog/PO data, normalize it, fill gaps, flag anomalies, connect it to a footprint. It deliberately stays narrow: no heavy ETL, no Airflow, no Spark, no data-warehouse plumbing. This proposal is built to that line.

### What this project deliberately is

- Applied Python + Pandas + SQL, with a thin, clean full-stack surface.
- Data-quality judgment: observed, derived, referenced, and imputed values stay distinct and labeled.
- NLP basics done well: regex, alias/typo handling, normalization, bounded fuzzy matching, composition parsing.
- Deterministic and reproducible end to end: same input + same rule versions → same output, byte-for-byte.
- Auditable: every published metric carries provenance and version metadata.
- A focused, correct use of an existing open-source lineage library (Bloodline), not a platform rewrite.

### What it deliberately is **not**

| Non-goal | Reason |
|---|---|
| A warehouse-style evidence graph (lineage tables, a DAG wrapper, a SQL-annotation DSL) | This *is* data-warehouse plumbing — deliberately out of scope. Provenance comes from Bloodline instead. |
| A trade-based footprint proxy on import weight | A product-level footprint should come from the BOM, not a trade-weight proxy. Footprint is computed on the BOM. |
| An auto-selecting imputation backtest harness | Model training is out of scope; this values judgment over method. Replaced by one fixed rule whose error is *measured* (QA), not a loop that *selects* a method. |
| A runtime LLM in the data path | Breaks reproducibility and auditability. AI is a build-time power tool (agentic engineering / Claude Code), not a data-path dependency. |
| Elaborate PII redaction / retention machinery | Data is synthetic and fictional. One paragraph ([§13](#13-privacy)) covers the real-data principle. |
| An upstream PR as a milestone gate | Merge timing isn't ours to schedule. Kept as an aspiration ([§11](#11-open-source-library-usage)). |

---

## 3. End result (definition of done)

A reviewer can, in one sitting:

1. Upload a deliberately messy apparel BOM file.
2. See schema-drift and mapping proposals **before** any unsafe processing.
3. See what parsed vs. what couldn't, and what looks wrong or implausible — flagged for review, not silently fixed.
4. See a clearly-labeled, component-level carbon estimate, with the share of inputs that were observed vs. filled, expressed with an uncertainty range.
5. Click any number and trace it — via Bloodline plus an append-only rule ledger — through the exact rules applied, back to the source file and row, and see the factor version used.
6. Understand what the pipeline can prove exactly, and what it represents as an assumption.

The submission is a clean repo, the fixture generator, tests, a five-minute walkthrough, and a short limitations note.

---

## 4. Architecture

```text
  ┌──────────────────────────────────────────────┐
  │ Source file (CSV / XLSX)  +  reference data   │
  └───────────────────┬──────────────────────────┘
                      │  1. ingest + profile + schema-drift gate
                      v
  ┌──────────────────────────────────────────────┐
  │ Python / Pandas connector  (@bloodline)       │
  │  normalize · validate · augment (fill ladder) │
  │  every step = a versioned deterministic rule  │
  └───────┬───────────────────────────┬──────────┘
          │ cleaned records +          │ rule-event ledger
          │ Bloodline data_lineage     │ (append-only history)
          v                            v
  ┌──────────────────────────────────────────────┐
  │ DuckDB  (optional query layer, small)         │
  │  footprint models · readiness · explanations  │
  └───────────────────┬──────────────────────────┘
                      v
  ┌──────────────────────────────────────────────┐
  │ One brand-facing view + provenance drawer     │
  └──────────────────────────────────────────────┘
```

Two provenance stores, by design (see [§8](#8-provenance-and-governance)):

- **Bloodline `data_lineage`** — the provenance *spine*: where each cell's current value comes from, inline, surviving joins.
- **Rule-event ledger** — the ordered *history*: one row per rule application, the log the provenance drawer and the fill-accuracy metric read from.

DuckDB is optional and local — a query surface for the views, not a warehouse. Lea and icanexplain are stretch only ([§11](#11-open-source-library-usage)).

---

## 5. Data sources

Real public data for reference/context; a clearly-fictional synthetic fixture for the connector problems public data can't exhibit.

| Source | Role | Notes |
|---|---|---|
| **Synthetic apparel BOM fixture** | **Primary input — the star.** Exercises parsing, normalization, validation, and gap-filling. | Deterministic generator; holds ground truth for QA ([§6](#6-canonical-model-and-fixture)). |
| **Ecobalyse / ADEME (Base Empreinte)** | **Material emission factors** (kgCO₂e/kg) for the footprint. | French-government open data, textile-specific, open API. Ships as a small versioned factor CSV with a citation per row. |
| **PEFCR (Apparel & Footwear)** and an **open LCA reference database** | **Verifiable reference** for plausibility bands and constant-value fallbacks ([§7.4](#74-the-fill-ladder)). | *Open item:* confirm whether the reference DB carries per-garment representative **weights** (for weight bands) or only material factors; if the latter, PEFCR supplies the weight reference. |
| **US Census textile imports** (`TEXCTYPT`, 2024–2025) | **Optional, secondary.** A genuinely ugly government CSV to prove ingestion (quoted fields with commas, blank/multi-part headers). Optional macro sanity panel. | *Not* the footprint base. |
| **Open Supply Hub API** | **Optional enrichment.** Fuzzy-match a messy `supplier_raw` to a real facility name — demonstrates entity resolution. | Always a *suggestion*, never verified fact. Cache responses; mind rate limits. |

**Dropped:** Textile Exchange knowledge center — it is articles, not a clean factor table; replaced by Ecobalyse/ADEME above.

---

## 6. Canonical model and fixture

### Canonical record (contract)

```text
record_id, source_row_id, style_id, sku, component,
material_raw, material_normalized, composition, component_weight_g,
supplier_raw, supplier_normalized, factory_country_iso,
order_date, quantity, unit_price, quality_status
```

### Fixture design — sized to the decision tree, not to impress

Volume is set so that **every branch of the fill ladder fires at least once on believable data**, and the whole thing can be walked through live. Large synthetic data is avoided: it reads as padding, can't be demoed, and can't manufacture real statistical signal.

| Parameter | Value | Rationale |
|---|---|---|
| Garment archetypes | 4 (t-shirt, hoodie, trousers, dress) | Gives a `category` dimension to back off across. |
| Styles | ~50 (~12 per archetype) | Dense groups clear support; niche ones don't. |
| Rows | ~500 component lines (~5–8 components/style) | Believable single-brand export, auditable live. Volume from real BOM structure, not inflation. |
| Suppliers | 4–5 entities, 2–4 messy spellings each | Fuzzy-match value comes from *variants of few entities*. |
| Weight missingness | ~30–40% of component rows | Enough observed weights to compute medians, enough gaps to make filling matter. |

### Planted cases (ground truth is known)

The generator **plants** each ladder branch and retains the true value of every corrupted or blanked cell:

- dense, tight groups that fill cleanly at the formula/median tier;
- a group with support but high spread → fails the dispersion guard → falls to reference;
- a sparse group → fails the support guard;
- an implausible planted outlier → trips the plausibility band;
- messy conditions: renamed headers, `Organic cottn`, `70/30 CO/PL`, mixed g/kg, blank vs. zero, duplicate keys, malformed dates, extreme price/weight.

Because ground truth is held, we can **measure** fill accuracy ([§12](#12-testing-and-qa)) — the one thing only synthetic data makes possible.

### Two vintages (for optional icanexplain)

The generator is parameterized so **v1 (2024)** and **v2 (2025)** differ in *controlled* ways — a volume change, a material-mix shift, one factor-version bump. Because the changes are planted, the ground-truth decomposition is known, making it the ideal test for icanexplain. Gated on the core landing.

---

## 7. Core pipeline

### 7.1 Everything is a versioned Data Augmentation Rule

Normalization and imputation are the **same kind of object**: a versioned, deterministic rule that takes inputs, applies a fixed transformation, and writes a record. A unit conversion, an ISO-country lookup, a `cottn→cotton` alias (fixed algorithm + fixed threshold + fixed reference = deterministic), a composition parse, a grouped-median fill, a reference constant — all share one record schema ([§8](#8-provenance-and-governance)). This single abstraction is the whole governance story and keeps the codebase small. (We use the term "Data Augmentation Rule" for this mechanism throughout.)

### 7.2 Ingest + schema-drift gate

Detect CSV/XLSX; store original bytes; content-hash; register the source and reject duplicate imports unless explicitly rerun (idempotent). Profile headers, types, null rates, cardinality, sample values; compare against the last accepted schema; **stop unsafe processing** on any add/remove/rename/type-change and emit a mapping-review proposal (deterministic aliases first).

### 7.3 Normalize + validate

- Parse dates, amounts, units; normalize weights to grams while preserving the raw value and unit; normalize countries via ISO lookup.
- Parse composition strings (`70/30 CO/PL` → `{cotton: .7, polyester: .3}`, checked to sum to 100%).
- Flag anomalies as reviewable events — validity (negative qty, invalid date), completeness (absent weight/country), duplicate keys, cross-field (composition ≠ 100%, value with zero qty), distribution (extreme weight or price/kg via log + median/MAD), and implausible claims (the "70% recycled"-style sanity flag). No silent edits.

### 7.4 The fill ladder

Applied per missing cell, **first match wins**, fully deterministic, LLM-free:

1. **Derive from a formula** — exact, when inputs are present (e.g. `component_weight = total_garment_weight × composition_pct`; `line_value = unit_price × quantity`). Preferred; no uncertainty caveat.
2. **Resolve against a reference** — canonical universes: country→ISO, unit, material vocabulary, factor table; includes bounded fuzzy match above a fixed threshold. Deterministic lookup.
3. **Grouped median with guards** — for genuine continuous numerics with no formula (in practice, essentially **only `component_weight`**). Take the **finest** group clearing both guards below; back off only as needed:
   - **Support:** `n ≥ N` observations in the group.
   - **Dispersion:** robust CV (`MAD / median`, or quartile coefficient of dispersion) `≤ c` — the deterministic form of "sufficiently low variance."
   - **Plausibility (verifiable source):** the resulting median must fall inside the reference band, else it is rejected and the ladder falls through to tier 4.
4. **Reference constant** — a citable value (PEFCR / open LCA reference DB / Ecobalyse), scoped to garment/material, marked as an assumption. This is both the fallback tier *and* the source of the tier-3 plausibility band.
5. **Leave null, flag `action required`** — the honest last resort, reached only when nothing above clears its bar.

This mirrors established data-quality practice (try methods one at a time; use a statistical model only with low variance; fall back to constants from agreed databases like PEFCR; track every decision; express uncertainty as a range) — minus the two tiers that need infrastructure out of scope for a single-file project (a trained model; a cross-customer repository). That subset is the correct scoping, not a shortfall.

### 7.5 Uncertainty

Filled values carry a **range**, not a bare point estimate — good governance, and honest about what the number rests on. The share of a footprint that rests on observed vs. filled inputs is surfaced in the view.

### 7.6 Thresholds (all versioned config, no magic numbers)

| Threshold | Default | Notes |
|---|---|---|
| Support `N` | 5 | Defensible floor for a median. |
| Back-off levels | 3: `material×component×category` → `component×category` → `category`, then **stop** | Stops *before* a meaningless global weight median. |
| Dispersion cutoff `c` | robust CV ≤ ~0.30 | Calibrated to sit between the fixture's planted tight/loose groups; documented as calibrated, not divined. |
| Plausibility band | `[0.3×, 3×]` reference weight, or the reference's own range | The external "does this make sense" check. |

Refusing to compute a statistic below level 3 (where groups stop being semantically coherent) is a **stated design decision** — the "spot what's wrong before it reaches a customer" instinct, made explicit.

---

## 8. Provenance and governance

Two complementary stores. Same records, two shapes, two consumers — not double bookkeeping.

### 8.1 Bloodline — the provenance spine

Bloodline (`@lineage`) adds a `data_lineage` column recording, per row × column, one source object `{source_type, source_metadata}`. Reads tag it automatically; merges fuse it; derived columns can inherit it; an ER diagram can be emitted from detected joins. Each fill records its method per row via:

```python
bl.apply_data_lineage(
    table=df,
    default_source=bl.Source(
        source_type="GROUPED_MEDIAN",
        source_metadata={
            "rule_id": "weight_median_v1",
            "group": "material×component×category",
            "n": 12,
            "dispersion": 0.18,
            "band_ref": "PEFCR_2023",
            "confidence": 0.82,
        },
    ),
    row_mask=weight_was_filled_here,
    column_names=["component_weight_g"],
    override=True,
)
```

Source type per ladder tier:

| Tier | `source_type` |
|---|---|
| Formula | `DERIVED_FORMULA` |
| Reference resolution / fuzzy match | `REFERENCE_RESOLVE` |
| Grouped median | `GROUPED_MEDIAN` |
| Reference constant | `REFERENCE_CONSTANT` |
| Normalization rules | `NORMALIZE_<kind>` |
| Untouched null | `UNKNOWN` |

**Known limit:** Bloodline stores the source of the *current* value (one object per cell; `override` replaces it). It does not keep the ordered lifecycle of every transformation — that is an open item on its roadmap. Hence the ledger.

### 8.2 Rule-event ledger — the ordered history

Append-only; one row per rule application:

```text
event_id, run_id, record_id, column,
rule_id, rule_version, source_type, method_params (json),
value_before, value_after, is_original_null, uncertainty_range, created_at
```

The ledger is what the provenance drawer reads, what the fill-accuracy metric aggregates over, and what satisfies "each transformation is tracked."

### 8.3 Governance properties (what this buys)

Immutable, content-hashed raw inputs (never mutated); additive transforms only; full lineage; reproducibility guaranteed by determinism (no LLM, nothing random, seeded config); observed/derived/referenced/imputed kept distinct; every reference versioned and cited; uncertainty recorded, never hidden.

---

## 9. Footprint

```text
estimated_kgco2e(component) = component_weight_kg × factor_kgco2e_per_kg(material)
```

Component-level, aggregated to product and catalog. Always display the factor source/version, material-mapping confidence, and observed-vs-filled input share, with an uncertainty range.

**Optional (stretch):** icanexplain decomposes v1→v2 change into volume/mix and intensity/factor effects; a reconciliation record checks the contributions sum to the observed delta within tolerance. Validated against the planted ground-truth decomposition ([§6](#6-canonical-model-and-fixture)).

---

## 10. Dashboard — one strong view, rebalanced

Effort goes to one genuinely usable brand-facing view rather than a second provenance subsystem.

- **Readiness panel:** schema-drift status; material/weight/country coverage; observed/derived/referenced/imputed shares; anomalies by severity and review status; prioritized next action.
- **Review queue:** anomalies, missing values, uncertain mappings — raw value, evidence, proposed rule, method, confidence, approve/reject. Approvals become versioned reusable rules, re-applied
to the corrected cell (Phase 8) with their lineage chained onto the original
source ([§8.1](#81-bloodline--the-provenance-spine)), not overwriting it.
- **Footprint + material basket:** estimate over material/category/country, with the factor/coverage/uncertainty labels.
- **Provenance drawer (per number):** `metric → footprint rows → rules applied → source file/row + factor version`, read from the ledger and the Bloodline spine.

---

## 11. Open-source library usage

Judgment = using few libraries well, not all of them. Each is used as intended, not wrapped or rebuilt.

| Library | Use | Boundary |
|---|---|---|
| **Bloodline** | **Core.** Row-level lineage spine. | Use it as intended; don't reimplement lineage. |
| **Lea** | *Stretch.* A tiny staging→core→mart DuckDB DAG, only to show analytics-engineering curiosity. | No wrapper, no annotation DSL, no warehouse. |
| **munpack / icanexplain** | *Stretch,* only with the two fixture vintages. | One narrow footprint explanation. |

**Contribution opportunity (aspiration, not a gate):** the source-vs-lifecycle gap in [§8.1](#81-bloodline--the-provenance-spine) is a real item in Bloodline's own backlog. An augmentation-rule provenance helper that preserves original lineage and attaches a rule record (rule/version, inputs, confidence) is a genuine, well-aimed contribution — with regression tests and an example drawn from this connector.

---

## 12. Testing and QA

### Fixture behavior tests

| Fixture | Expected |
|---|---|
| Renamed header | schema-drift warning, review required |
| `Organic cottn` | proposed alias, not silent correction |
| `70/30 CO/PL` | composition parsed, sums to 100% |
| mixed g/kg | normalized value + preserved raw value/unit |
| blank weight, dense tight group | filled by grouped median, `GROUPED_MEDIAN` lineage |
| blank weight, high-spread group | fails dispersion → reference constant |
| blank weight, sparse group | fails support → reference constant |
| implausible weight | trips plausibility band → rejected/flagged |
| zero weight / positive value | high-severity anomaly |
| duplicate key | finding, no double counting |
| duplicate file upload | idempotent rerun, no duplicate rows |
| factor-table revision | recalculated metrics + factor-version diff |

### Fill-accuracy metric (QA, not method selection)

Because ground truth is held, report the measured error of the **fixed** rule — e.g. grouped-median fills weight to within *X%* MAE on held-out truth; reference-constant fallback to within *Y%*. Measuring a fixed rule is QA. Selecting among methods by score is the overbuilt alternative this deliberately avoids.

### Determinism / reproducibility

Re-running unchanged inputs and config yields identical outputs, identical lineage, identical ledger. A changed factor version yields a new calculation version without corrupting historical records.

---

## 13. Privacy

Inputs are synthetic and fictional; no real customer data is used. In production, the same design supports it: minimal handling of supplier/pricing fields, a stated retention/deletion policy, and no external transfer of customer data — but none of that machinery is built here.

---

## 14. Milestones (lean, re-sequenced)

| # | Deliverable | Gate |
|---|---|---|
| 1 | Contract + fixture generator (with planted cases + ground truth) | every ladder branch has a fixture with a specified expected outcome |
| 2 | Connector MVP: ingest, content-hash, idempotency, schema-drift gate, mapping review | clean and changed-schema imports run correctly |
| 3 | Normalize + validate + anomaly events | review queue supports approve/reject with history |
| 4 | Fill ladder + rule ledger + Bloodline lineage | every fill labeled with tier + params; fill-accuracy metric reported |
| 5 | Footprint + one brand-facing view + provenance drawer | reviewer completes the end-to-end journey and traces a number to source |
| 6 *(stretch)* | Lea DAG and/or icanexplain on two vintages | repeatable metric with a reconciled explanation |
| 7 *(aspiration)* | Bloodline augmentation-rule helper | regression tests + documented example |
| 8 | Demo + limitations note | repeatable five-minute walkthrough |

---

## 15. Claims boundaries

**May claim:** a field was read from a named file/row; a value was normalized/derived/referenced/imputed by a named versioned rule; a metric was computed by a versioned model from defined inputs; a footprint is a labeled estimate with stated coverage and factor assumptions.

**Must not claim:** an imputed value is exact; an identifier can be statistically guessed; an anomaly is erroneous without a review decision; a footprint is precise where it rests materially on filled inputs.

---

## 16. Build phases (actionable execution plan)

§14 lists *what* ships and its acceptance gate. This section turns that into an *ordered, buildable* plan: each phase names its objective, the concrete tasks, the exit gate that must be green before the next phase starts, and the build harness (`.claude/skills/` + `.claude/hooks/`) that governs it. Phases are sequential; a phase is done only when its gate passes on a clean re-run.

**Cross-cutting rules (every phase, no exceptions).**

- **Determinism is a gate, not a goal.** Same input + same rule versions ⇒ byte-identical output, lineage, and ledger. No LLM, no unseeded randomness, no wall-clock in the data path. The `determinism-guard` hook enforces this on every Python edit.
- **Everything is a versioned Data Augmentation Rule.** No transformation lands without a `rule_id` + `rule_version` and a lineage/ledger record ([§7.1](#71-everything-is-a-versioned-data-augmentation-rule), [§8](#8-provenance-and-governance)).
- **One runnable check per non-trivial unit.** Prefer a doctest that doubles as documentation; a `test_*.py` when a doctest would be contorted ([§12](#12-testing-and-qa)). No feature is "done" without its check.
- **Ship the lazy version first.** Climb the reuse ladder (`carbonara-craft`) before writing new code; use Bloodline as intended rather than reimplementing lineage. Mark any deliberate corner-cut with a `# ponytail:` comment naming its ceiling.
- **The code must read as house style.** `carbonara-craft` (idioms/structure) and `carbonara-voice` (commits/PRs/comments/docstrings) apply to every file and every commit.

Effort setting for the build: **Opus 4.8 at `xhigh`** (the Anthropic-recommended default for coding/agentic work). Specify task + intent + constraints upfront; keep interactive turns few.

| Phase | Objective | Milestone |
|---|---|---|
| 0 | Build harness + repo skeleton | — (this task) |
| 1 | Contract + fixture generator | M1 |
| 2 | Ingest + schema-drift gate | M2 |
| 3 | Normalize + validate + anomaly events | M3 |
| 4 | Fill ladder + ledger + Bloodline lineage | M4 |
| 5 | Footprint + view + provenance drawer | M5 |
| 6 | *(stretch)* Lea DAG / icanexplain | M6 |
| 7 | *(aspiration)* Bloodline helper | M7 |
| 8 | Demo + limitations note | M8 |

### Phase 0 — Build harness + repo skeleton

**Objective.** Stand up the deterministic-by-default toolchain and the skills/hooks that keep every later phase honest, before any product code exists.

- Initialize the package layout (`carbonara/` connector package, `tests/`, `references/` for versioned factor/reference CSVs, `fixtures/`).
- `pyproject.toml`: Python ≥ 3.11, uv build backend, ruff (line-length 120; `E,W,F,I,B,UP`), ty, pytest with `--doctest-glob=*.md`. Pin `pandas`, `duckdb`, `bloodline`.
- `.pre-commit-config.yaml`: uv-lock, ruff-check `--fix`, ruff-format, ty — on pre-push.
- Install the build harness: `.claude/skills/` (craft, correctness, voice, efficiency), `.claude/hooks/` (determinism guard, ruff-on-edit), `.claude/settings.json`.
- Apply the documentation voice (`carbonara-voice`) to this document: keep it a standalone final proposal that describes only what the project does and what it will show — current design stated as the plan, no changelog or "what changed" narrative, no company named, no job-role or application framing, hype removed. Reapply whenever the spec is edited.
- **Exit gate.** `uv run pytest` runs green on an empty suite; `pre-commit run --all-files` passes; the determinism guard blocks a deliberately-planted `datetime.now()` in `carbonara/`; this proposal reads standalone (no changelog framing, no company name, no application/role framing).

### Phase 1 — Contract + fixture generator *(M1)*

**Objective.** A deterministic generator that emits one messy BOM and retains ground truth for every corrupted/blanked cell.

- Freeze the canonical record ([§6](#6-canonical-model-and-fixture)) as a typed contract (a frozen dataclass / explicit schema).
- Build the generator: 4 archetypes, ~50 styles, ~500 component lines, 4–5 suppliers with messy spellings, ~30–40% weight missingness. `random.seed(...)` fixed; ground-truth table written alongside the corrupted file.
- **Plant every ladder branch** ([§6](#6-canonical-model-and-fixture)): dense/tight, high-spread, sparse, planted outlier, plus messy conditions (renamed headers, `Organic cottn`, `70/30 CO/PL`, mixed g/kg, blank-vs-zero, duplicate keys, malformed dates, extreme price/weight).
- **Exit gate.** Every fill-ladder branch and every row of the §12 fixture-behavior table has a fixture with a *specified expected outcome*; regenerating twice yields byte-identical files.

### Phase 2 — Ingest + schema-drift gate *(M2)*

**Objective.** Safely admit a file: detect it, hash it, refuse silent drift.

- Detect CSV/XLSX; store original bytes; content-hash; register source; reject duplicate imports unless explicitly rerun (idempotent).
- Profile headers/types/null-rates/cardinality/sample values; diff against last accepted schema; **stop unsafe processing** on any add/remove/rename/type-change and emit a deterministic mapping-review proposal (aliases first).
- **Exit gate.** A clean file imports; a changed-schema file halts with a mapping proposal; re-uploading the same bytes is a no-op. Fixture tests from §12 (renamed header, duplicate file) pass.

### Phase 3 — Normalize + validate + anomaly events *(M3)*

**Objective.** Turn raw cells into normalized values and reviewable findings — never silent edits.

- Normalization rules (each versioned): dates, amounts, units→grams (preserve raw value+unit), country→ISO, composition parse (`70/30 CO/PL` → fractions summing to 100%).
- Anomaly detection as events: validity, completeness, duplicate-key, cross-field, distribution (log + median/MAD), implausible-claim ([§7.3](#73-normalize--validate)).
- Review queue with approve/reject + history; approvals become versioned reusable rules.
- **Exit gate.** Review queue supports approve/reject with history; the §12 normalization/anomaly fixtures each produce the specified event (proposed alias, parsed composition, preserved raw unit, high-severity zero-weight, etc.).

### Phase 4 — Fill ladder + rule ledger + Bloodline lineage *(M4)*

**Objective.** Fill gaps by the first-match-wins ladder, and prove how each fill was made.

- Implement the ladder ([§7.4](#74-the-fill-ladder)): formula → reference resolve (incl. bounded fuzzy) → grouped median with support/dispersion/plausibility guards → reference constant → leave-null. All thresholds are versioned config ([§7.6](#76-thresholds-all-versioned-config-no-magic-numbers)); no magic numbers.
- Every fill writes a Bloodline `Source` (tier→`source_type`, [§8.1](#81-bloodline--the-provenance-spine)) **and** an append-only ledger row ([§8.2](#82-rule-event-ledger--the-ordered-history)). Filled values carry an uncertainty range.
- Fill-accuracy metric against held-out ground truth (QA of a *fixed* rule — not method selection, [§12](#12-testing-and-qa)).
- **Exit gate.** Every fill is labeled with its tier + params in both stores; the fixture cases route to the expected tier (tight→median, high-spread/sparse→constant, implausible→rejected); fill-accuracy is reported; a re-run reproduces lineage and ledger exactly.

### Phase 5 — Footprint + brand-facing view + provenance drawer *(M5)*

**Objective.** Compute the estimate and let a reviewer trace any number to source. This is the full-stack deliverable — one strong view.

- Footprint: `component_weight_kg × factor(material)`, aggregated to product/catalog, with factor source/version, mapping confidence, observed-vs-filled share, uncertainty range ([§9](#9-footprint)).
- One brand-facing view ([§10](#10-dashboard--one-strong-view-rebalanced)): readiness panel, review queue, footprint + material basket, provenance drawer (`metric → footprint rows → rules applied → source file/row + factor version`).
- Frontend follows the design guidance in `carbonara-craft` — this is a data/dev tool, **not** an editorial page: specify a concrete, restrained visual direction; do not accept the default cream/serif house style.
- **Exit gate.** A reviewer completes the end-to-end journey and traces one displayed number back to its source row and factor version; a factor-table revision recomputes metrics and shows a version diff without corrupting history.

### Phase 6 — *(stretch)* Lea DAG and/or icanexplain *(M6)*

Gated on Phase 5 landing. A tiny staging→core→mart DuckDB DAG (no wrapper, no DSL), and/or icanexplain decomposing v1→v2 into volume/mix vs. intensity/factor, reconciled against the planted ground-truth decomposition ([§6](#6-canonical-model-and-fixture), [§9](#9-footprint)). **Exit gate.** A repeatable metric with a reconciled explanation that sums to the observed delta within tolerance.

### Phase 7 — *(aspiration)* Bloodline augmentation-rule helper *(M7)*

Gated, and merge timing is not ours ([§11](#11-open-source-library-usage)). A helper that preserves original lineage while attaching a rule record (rule/version, inputs, confidence), with regression tests and an example drawn from this connector. **Exit gate.** Regression tests pass; a documented example runs as a doctest.

### Phase 8 — Demo + limitations note *(M8)*

**Objective.** Make the story repeatable in five minutes, with the review loop applied end to end.

- **Apply the review loop.** Wire `review.approved_rules()` back into the pipeline as a second pass: an approved mapping (e.g. `Organic cottn` → `organic cotton`) is re-applied to the cell it corrects, not merely minted. The re-apply pass attaches its lineage with `carbonara.augment.augment_lineage` (Phase 7), so the reviewer's rule **chains onto the cell's original source** (normalize → approved alias) instead of clobbering it ([§8.1](#81-bloodline--the-provenance-spine)); it writes a ledger event like any rule ([§8.2](#82-rule-event-ledger--the-ordered-history)). The decision (actor, status, timestamp) is injected, so the pass stays deterministic.
- A scripted, deterministic walkthrough (upload → drift gate → review → **approve → re-run** → fill → footprint → provenance trace) that shows a chained cell lineage in the provenance drawer; a short limitations note ([§15](#15-claims-boundaries)); README with tested doctests.
- **Exit gate.** The five-minute walkthrough is reproducible from a clean checkout; an approved mapping re-applies and its cell carries a two-entry lineage (original + approval); `uv run pytest` (unit + doctest + README) is green; claims in the README stay inside the [§15](#15-claims-boundaries) boundaries.

---

*In one line: a connector that makes messy data usable without hiding uncertainty, then proves — deterministically — where every reported number came from.*
