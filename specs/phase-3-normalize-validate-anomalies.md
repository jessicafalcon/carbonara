# Phase 3 — Normalize + validate + anomaly events

Branch `phase-3-normalize-validate-anomalies`. Implements milestone M3 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, per §7.1 and §7.3.

## Objective

Turn the raw cells of an accepted import into normalized values, and turn every
problem into a reviewable finding — never a silent edit. Each transformation is a
versioned, deterministic rule that records what it did; each anomaly is an event
with a severity and a review decision that carries its own history. This phase
does **not** fill missing values (Phase 4) or compute a footprint (Phase 5).

## What the fixture actually contains

The rules are sized to `fixtures/bom_v1.csv`, not to a hypothetical file:

| Column | Shape in the fixture | Rule |
|---|---|---|
| `country` | 5 clean names (China, India, Portugal, Sweden, Vietnam) | resolve to ISO-3166 alpha-2 |
| `material` | 7 values incl. one typo (`Organic cottn`) | normalize to vocabulary; propose on a near-miss |
| `supplier` (as `vendor`) | 17 spellings of ~5 entities | fuzzy-normalize to the canonical name above threshold |
| `composition` | `100% cotton`, `70/30 CO/PL`, `80% cotton / 20% polyester` | parse to fractions summing to 1.0 |
| `net_weight` | `200 g`, `0.42 kg`, `0 g`, blanks | parse to grams, preserve raw value+unit |
| `order_date` | ISO dates, a few malformed | parse to a date; malformed → validity anomaly |
| `quantity` / `unit_price` | clean integer / float | coerce; flag out-of-range or extreme values |

## Design decisions

- **One rule abstraction (§7.1).** Normalization and (later) imputation share one
  record: a `RuleEvent` — `rule_id`, `rule_version`, `source_type`, params,
  `value_before`, `value_after`, `is_original_null`. Phase 3 emits it for
  normalizations; Phase 4 reuses it for fills and adds the append-only ledger file
  and Bloodline `Source`. Building it once here avoids rework.
- **Findings are separate from transformations.** An anomaly or an uncertain
  mapping is a `Finding` (category, severity, evidence, proposed value, review
  history) — a thing to *decide*, not a value that changed. The review queue owns
  findings; approving one yields a versioned reusable rule.
- **The canonical frame.** Rules operate on a pandas frame keyed to
  `CANONICAL_COLUMNS`, raw columns preserved beside their normalized forms
  (`material_raw`/`material_normalized`, `net_weight` raw beside
  `component_weight_g`). The per-value functions stay pure and doctested; the pass
  applies them across the frame. Aligns with the Phase 4/5 frame + DuckDB path.
- **Confident vs uncertain, split by footprint impact.** Suppliers do not drive
  the footprint, so a high-confidence fuzzy match is applied and logged (visible,
  not silent). Materials do drive it (§15 claims boundary), so a near-miss like
  `Organic cottn` is a *proposal* left for review, not an applied correction.
- **Determinism.** Fuzzy match is `difflib` above a fixed threshold; distribution
  uses `statistics` median/MAD; all thresholds are versioned config, no magic
  numbers. No wall-clock: `RuleEvent`/`Finding` ids are composite and stable, and
  a review decision takes an injected actor/timestamp, never `datetime.now()`.

## Anomaly categories (§7.3)

Emitted as `Finding`s with a severity:

- **validity** — invalid date, negative quantity.
- **completeness** — absent weight or country.
- **duplicate-key** — repeated `(style_id, sku, component)`; flagged, counted once.
- **cross-field** — composition ≠ 100%; positive value on zero weight/quantity.
- **distribution** — extreme `component_weight_g` or `unit_price` by log +
  median/MAD beyond a fixed cutoff.

## Deliberately out of scope

- **Filling missing values.** The blank-weight cases and the whole fill ladder are
  Phase 4; Phase 3 flags a missing weight as a completeness finding and stops.
- **Plausibility band on a fill.** The `[0.3×, 3×]` reference band rejects a
  *filled* value (Phase 4). An extreme *observed* value is caught here as a
  distribution anomaly.
- **A currency/thousands amount parser.** `quantity` and `unit_price` arrive as
  clean numerics in this fixture; parsing is a type coercion, and a dedicated
  amount parser would be speculative (brief §2). Added when a file needs it.
- **Implausible-claim detection.** The fixture carries no recycled-content or
  claims field for the "70% recycled" sanity flag to act on; deferred until such a
  field exists.
- **Persistent ledger + Bloodline lineage.** Phase 4. Phase 3 returns events and
  findings in memory (the review queue serializes its findings and decisions).

## Reference data (`references/`, one citation per row)

- `countries_iso_v1.csv` — the fixture's countries → ISO-3166 alpha-2.
- `materials_v1.csv` — canonical material vocabulary + shorthand codes
  (`CO→cotton`, `PL→polyester`), for both material normalization and composition
  parsing (source: Ecobalyse material list).
- `suppliers_v1.csv` — the canonical supplier names to fuzzy-match against
  (fixture-defined entities).

## Ordered steps (one commit each)

1. **Spec** — this file.
2. **Records.** `carbonara/rules.py`: `SourceType` (§8.1), `Severity`, `RuleEvent`,
   `Finding` frozen dataclasses with deterministic ids. Doctest + tests.
3. **Reference data.** The three `references/*.csv` files and
   `carbonara/references.py` — deterministic loaders returning frozen mappings.
   Tests.
4. **Materialize.** `carbonara/materialize.py`: build the canonical frame from an
   accepted import and a confirmed column mapping; assign deterministic
   `record_id`; set raw fields, leave normalized fields null. Tests.
5. **Value normalizers.** `carbonara/normalize.py`: dates, units→grams (preserve
   raw), composition parse (with codes). Pure functions + doctests.
6. **Reference normalizers.** Same module: country→ISO, supplier fuzzy-normalize,
   material typo→proposal. The `normalize_frame` pass applying all rules, emitting
   `RuleEvent`s and material-proposal `Finding`s. Tests.
7. **Anomalies.** `carbonara/anomalies.py`: validity, completeness, duplicate-key,
   cross-field, distribution detectors → `Finding`s. Tests per category.
8. **Review queue.** `carbonara/review.py`: hold findings, approve/reject with
   history, approvals become versioned rules. Tests.
9. **§12 fixture-behavior + determinism.** Run normalize + validate over
   `bom_v1.csv` (with the approved `vendor → supplier` mapping); assert each §12
   Phase 3 case produces its specified event, and that a re-run is identical.

## Exit gate (brief §16)

- The review queue supports approve/reject with history; an approval yields a
  versioned rule.
- Each §12 normalization/anomaly fixture produces its specified event: material
  typo → proposed alias (not silent), `70/30 CO/PL` → composition summing to 1.0,
  mixed g/kg → grams with raw preserved, zero weight + positive value →
  high-severity anomaly, duplicate key → finding, malformed date → validity
  anomaly, extreme price → distribution anomaly, supplier variant → fuzzy match
  above threshold.
- `uv run pytest` and `uv run pre-commit run --all-files` are green; re-running the
  normalize + validate pass on unchanged input yields identical values, events,
  and findings.
