# Phase 1 — Contract + fixture generator

Branch `phase-1-contract-and-fixture`. Implements milestone M1 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16.

## Objective

Freeze the canonical record as a typed contract, and build a deterministic
generator that emits one messy apparel BOM while retaining the true value of
every corrupted or blanked cell. This fixture is the input every later phase is
tested against, and its ground truth is what makes fill accuracy measurable.

## Deliverables

```text
carbonara/contract.py          the canonical record (frozen dataclass) + column order + quality_status enum
fixtures/generate.py           deterministic generator (seeded; lives outside carbonara/ because it uses randomness)
fixtures/bom_v1.csv            the generated messy BOM (the connector's input)
fixtures/ground_truth_v1.csv   the true value of every corrupted/blanked cell, keyed by record
tests/test_contract.py         contract shape + quality_status values
tests/test_generate.py         determinism + every planted case is present with its expected outcome
```

The generator lives in `fixtures/`, not `carbonara/`: it uses seeded randomness,
which the connector package forbids (`carbonara-correctness` §1). It imports the
contract from `carbonara.contract`.

## The contract

The canonical record (brief §6), as a frozen, slotted, keyword-only dataclass,
with an explicit column order and a `quality_status` enum:

```text
record_id, source_row_id, style_id, sku, component,
material_raw, material_normalized, composition, component_weight_g,
supplier_raw, supplier_normalized, factory_country_iso,
order_date, quantity, unit_price, quality_status
```

## Generator design

Sized to the decision tree, not to impress (brief §6): every ladder branch fires
at least once on believable data, and the whole file is small enough to walk
through live.

| Parameter | Value |
|---|---|
| Garment archetypes | 4 (t-shirt, hoodie, trousers, dress) |
| Styles | ~50 (~12 per archetype) |
| Rows | ~500 component lines (~5–8 components/style) |
| Suppliers | 4–5 entities, 2–4 messy spellings each |
| Weight missingness | ~30–40% of component rows |
| Seed | fixed (`random.seed`), so output is byte-identical across runs |

## Planted cases (ground truth retained)

Each case is planted deliberately and its true value kept in `ground_truth_v1`:

- a dense, tight group that fills cleanly at the formula/median tier;
- a group with support but high spread (fails the dispersion guard);
- a sparse group (fails the support guard);
- an implausible planted outlier (trips the plausibility band);
- messy conditions: renamed headers, `Organic cottn`, `70/30 CO/PL`, mixed g/kg,
  blank vs. zero, duplicate keys, malformed dates, extreme price/weight.

## Determinism

Regenerating twice yields byte-identical `bom_v1.csv` and `ground_truth_v1.csv`.
No wall-clock, no unseeded randomness; ordering is stable before serialization.

## Steps (one commit each)

Work these in order; each is a single atomic commit, made once green.

1. **Contract** — `carbonara/contract.py` (record dataclass, column order,
   `quality_status` enum) + `tests/test_contract.py`.
   `feat(contract): add canonical record and quality_status`
2. **Generator base** — `fixtures/generate.py`: seeded generator emitting clean,
   valid rows across the archetypes/styles/suppliers.
   `feat(fixture): generate clean base BOM rows`
3. **Messy conditions** — plant renamed headers, `Organic cottn`, `70/30 CO/PL`,
   mixed g/kg, blank vs. zero, duplicate keys, malformed dates, extreme values.
   `feat(fixture): plant messy parsing conditions`
4. **Ladder cases** — plant dense-tight, high-spread, and sparse groups, an
   implausible outlier, and the ~30–40% weight-missingness band.
   `feat(fixture): plant fill-ladder group cases`
5. **Ground truth** — emit `ground_truth_v1.csv` with the true value of every
   corrupted/blanked cell.
   `feat(fixture): retain ground truth for planted cases`
6. **Tests** — generation determinism (byte-identical re-run) + presence and
   labeling of every planted case + missingness band.
   `test(fixture): determinism and planted-case coverage`
7. **Artifacts** — commit the generated `fixtures/bom_v1.csv` and
   `fixtures/ground_truth_v1.csv`.
   `chores(fixture): add generated bom_v1 and ground truth`

## Tests

- `test_contract.py`: the record has the specified fields in order; `quality_status`
  values are the fixed set.
- `test_generate.py`: two generations are byte-identical; each planted case is
  present and labeled with the branch it is meant to exercise; missingness sits in
  the target band.
- Doctests where they read well (e.g. a small contract example).

## Exit gate

Every fill-ladder branch and every row of the brief §12 fixture-behavior table
has a fixture case with a specified expected outcome; regenerating twice is
byte-identical; `uv run pytest` and `uv run pre-commit run --all-files` are green.

## Out of scope (later phases)

Ingest / schema-drift gate (Phase 2), normalization and anomaly events (Phase 3),
the fill ladder and ledger (Phase 4). Phase 1 only produces the contract, the
fixture, and its ground truth.
