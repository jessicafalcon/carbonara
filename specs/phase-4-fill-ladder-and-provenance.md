# Phase 4 — Fill ladder + rule ledger + Bloodline lineage

Branch `phase-4-fill-ladder-and-provenance`. Implements milestone M4 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, per §7.4–7.6 and §8.

## Objective

Fill missing `component_weight_g` by the first-match-wins ladder, prove how each
fill was made in both provenance stores (Bloodline `Source` + append-only
ledger), attach an uncertainty range to every filled value, and measure the fixed
rule's accuracy against held-out ground truth. Deterministic throughout: a re-run
reproduces fills, lineage, and ledger byte-for-byte.

## What the ladder actually fills

The only missing continuous cell in the fixture is `component_weight_g` (~30% of
rows). Categorical gaps were resolved in Phase 3; material typos are review
proposals, not auto-fills. The brief's five tiers are all realized across the
pipeline, first-match-wins per missing cell — a missing weight enters at tier 3
because tiers 1–2 have no applicable input for a weight gap, by the fixture's
design, not by omission:

1. **Formula** — the weight formula (`total_garment_weight × composition_pct`)
   needs a garment-total column the source does not carry, so no weight gap has
   formula inputs. The `DERIVED_FORMULA` mechanism is not dead vocabulary: it is
   exercised by the footprint (`component_weight × factor`) in Phase 5, the
   project's central formula derivation.
2. **Reference-resolve** — already realized at normalization (Phase 3):
   country→ISO, material vocabulary, supplier fuzzy-match are exactly "resolve
   against a canonical reference, bounded fuzzy above a threshold." A continuous
   weight is not reference-resolvable, so this tier is not re-run in the fill pass.
3. **Grouped median with guards** — the working tier for a weight gap.
4. **Reference constant** — the citable fallback, and the source of the tier-3
   plausibility band.
5. **Leave null, `action_required`** — the honest last resort.

So Phase 4 implements tiers 3–5 (the tiers a weight gap reaches); tiers 1–2 are
realized elsewhere in the pipeline, and the ladder's structure and this reasoning
are made explicit in `fill.py`. The exit gate confirms the tier routing.

## The grouped-median tier (§7.4, §7.6)

For a missing weight, compute the median of **observed positive** weights
(blanks and zeros excluded) in the finest group that clears both guards, backing
off only as needed:

| Back-off level | Group key |
|---|---|
| 1 (finest) | `material × component × category` |
| 2 | `component × category` |
| 3 | `category`, then **stop** |

- **Support:** `n ≥ N` (N = 5).
- **Dispersion:** robust CV `MAD / median ≤ c` (c = 0.30). Calibrated: the
  dense-tight group sits at CV ≈ 0.10, the high-spread group at ≈ 0.63.
- **Plausibility (on the result):** the median must fall inside the component's
  reference band, else the tier is rejected and the ladder falls to tier 4. The
  median is computed over all observed positives — it is robust to a lone
  outlier, and the guard protects the *output*, not the inputs.

`category` is the garment archetype, derived from the `style_id` prefix
(`TSH`/`HOO`/`TRO`/`DRS`). `material` is `material_normalized`, falling back to
the raw material when a proposal left it null.

If no level clears both guards, fall through to the reference constant.

## Reference constant, band, and uncertainty (§7.5)

`references/reference_weights_v1.csv` gives, per component, a representative
`ref_weight_g` and an explicit plausibility band `[band_low_g, band_high_g]`.
The band is `[0.3×, 3×]` the reference by default, widened to the reference's own
range where a component's natural spread is wider than 10× (webbing strap) — the
brief's stated alternative. This one table is the tier-4 constant, the tier-3
plausibility guard, and the observed-value check.

Every filled value carries an uncertainty range:

- **grouped median:** `[median − MAD, median + MAD]`.
- **reference constant:** the reference band, marked as an assumption.

A weight left null carries no range and is flagged `action_required`.

## Plausibility on observed values (the implausible case)

The implausible fixture case is an *observed* 5000 g shell (not a gap). A
validation pass flags any observed `component_weight_g` outside its component
band as `FLAGGED` — reviewable, never silently changed. This is distinct from
Phase 3's data-driven distribution anomaly (median/MAD); here the check is
against the verifiable reference band.

## Dual provenance (§8)

Every fill writes **both** stores:

- **Bloodline `Source`** on the cell via `bl.apply_data_lineage(..., row_mask=,
  column_names=["component_weight_g"], override=True)`, `source_type` = the tier
  (`GROUPED_MEDIAN` / `REFERENCE_CONSTANT` / `UNKNOWN`), `source_metadata` = the
  rule id, group, n, dispersion, band ref, confidence.
- **Ledger row** (§8.2): `event_id, run_id, record_id, column, rule_id,
  rule_version, source_type, method_params, value_before, value_after,
  is_original_null, uncertainty_range, created_at`. Append-only, deterministically
  serialized. `run_id` and `created_at` are **injected** (derived from the input
  content hash / passed by the caller), never read from the clock or a uuid.

The ledger extends the Phase 3 `RuleEvent` with `run_id`, `created_at`, and
`uncertainty_range`; normalization and fills write the same record (§7.1).

## Fill-accuracy metric (QA, not method selection — §12)

Because the generator holds ground truth, report the fixed rule's error against
`ground_truth_v1.csv` for the filled rows: MAE / MAPE overall and per tier
(grouped median vs reference constant). Reported, never gated on a tuned
threshold — measuring a fixed rule is QA; selecting methods by score is the
overbuild this avoids.

## Deliberately out of scope

- A fill-ladder tier 1 (formula) and tier 2 (reference-resolve) in the fill pass:
  tier 2 is realized at normalization (Phase 3) and the `DERIVED_FORMULA`
  mechanism at the footprint (Phase 5); a weight gap has no formula input. This is
  where those tiers live, not a gap to fill (above).
- The footprint and the brand-facing view (Phase 5).
- Filling categorical gaps or applying approved material aliases (Phase 3 owns
  proposals; applying an approved alias is a re-run with the minted rule).

## Ordered steps (one commit each)

1. **Spec** — this file.
2. **Reference weights.** `references/reference_weights_v1.csv` + a
   `reference_weights()` loader and `ReferenceWeight` record in
   `carbonara/references.py`. Tests.
3. **Fill source types + uncertainty.** Extend `SourceType` with the fill tiers
   and add `uncertainty_range` to `RuleEvent` in `carbonara/rules.py`. Tests.
4. **Fill ladder.** `carbonara/fill.py`: grouped median (guards + back-off) →
   reference constant → leave null, plus the observed-value plausibility check;
   emits fill `RuleEvent`s, uncertainty, and findings. Tests per tier.
5. **Ledger.** `carbonara/ledger.py`: `LedgerRow` (§8.2) and an append-only
   `Ledger` with injected `run_id`/`created_at` and deterministic serialization.
   Tests.
6. **Bloodline lineage.** `carbonara/lineage.py`: build a frame from records and
   apply a Bloodline `Source` per touched cell by tier. Tests.
7. **Fill accuracy.** `carbonara/accuracy.py`: MAE/MAPE of filled weights vs
   ground truth, overall and per tier. Tests.
8. **§12 fixtures + determinism.** End-to-end normalize → fill over `bom_v1`:
   dense-tight → median, high-spread/sparse → constant, implausible → flagged;
   both stores label every fill with its tier + params; a re-run reproduces
   fills, ledger, and lineage; accuracy is reported.

## Exit gate (brief §16)

- Every fill is labeled with its tier + params in both stores.
- The fixture cases route to the expected tier: tight → median, high-spread and
  sparse → constant, implausible → flagged/rejected.
- Fill accuracy is reported (per tier, against ground truth).
- A re-run reproduces fills, lineage, and ledger exactly.
- `uv run pytest` and `uv run pre-commit run --all-files` are green.
