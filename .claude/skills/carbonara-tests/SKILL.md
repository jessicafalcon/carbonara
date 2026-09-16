---
name: carbonara-tests
description: >
  The testing standard for the carbonara BOM connector — what to test, how, and
  to what bar. Covers the doctest-as-documentation style, the test taxonomy
  (doctest / unit / determinism / QA-metric), determinism and reproducibility
  tests, the §12 fixture-behavior cases, the fill-accuracy metric against planted
  ground truth, and the offline/no-network rule. Read this BEFORE writing or
  changing any test, or when deciding what a change needs to prove. Pairs with
  carbonara-craft (how code is written) and carbonara-correctness (the invariants
  a test defends).
---

# carbonara-tests

Tests are a first-class deliverable here, not an afterthought — the product
promise (reproducible, traceable numbers) is only as good as the tests that pin
it down. Tests must themselves be deterministic and offline.

## The bar

- **One runnable check per non-trivial unit** — the smallest thing that fails if
  the logic breaks. No per-function suites for trivial one-liners (YAGNI applies
  to tests too), no fixture pyramids the logic doesn't need.
- **Every invariant that matters has a test that fails when it's violated.** A
  rule with no test that would catch its regression is unfinished.
- **Fast and offline.** `uv run pytest` is the whole story; no network, no clock,
  no external service. External data is stubbed from a versioned fixture.

## Test taxonomy

Pick the lightest form that proves the behavior.

1. **Doctest (preferred)** — proves behavior *and* documents usage. Test-function
   bodies are often a pure `>>>` narrative; the README's `>>>` blocks are run too
   (via `tests/test_readme.py`). Use for the happy path and the illustrative case.
   ```python
   def test_parse_composition():
       """
       >>> from carbonara.normalize import parse_composition
       >>> parse_composition("70/30 CO/PL")
       {'cotton': 0.7, 'polyester': 0.3}
       """
   ```
2. **Unit test (`test_*.py`)** — when a doctest would be contorted: large frames,
   error paths, parametrized cases, float tolerances. AAA shape (arrange, act,
   assert); name the behavior:
   `test_high_spread_group_falls_through_to_reference_constant`.
3. **Determinism test** — see below; the invariant that same input ⇒ identical
   output/lineage/ledger.
4. **QA metric (fill-accuracy)** — measures a *fixed* rule's error against held-out
   ground truth; reported, not asserted as pass/fail on a tuned threshold.

## Determinism & reproducibility tests

The core guarantee, so it gets explicit coverage:

- **Byte-identical re-run.** Run the pipeline twice on the same input + config;
  assert equal output frame, equal `data_lineage`, equal ledger rows.
- **Seeded fixtures.** Any generator used in a test seeds `random.seed(42)` (and
  any numpy RNG) so the corpus is stable across runs and machines.
- **No wall-clock / uuid leak.** Timestamps and ids are injected, so a re-run
  compares equal. If a test needs a timestamp, pass a fixed one.
- **Version bump, not mutation.** Assert that changing a factor/rule version
  yields a *new* calculation version and leaves historical records intact.

## Fixture-behavior tests (the §12 table)

Every row of [§12 of the spec](../../../PROJECT-BRIEF.md) is a test with a named
expected outcome. Each planted fixture case ([§6](../../../PROJECT-BRIEF.md))
asserts the branch it was planted to exercise — e.g.:

- renamed header → schema-drift warning, review required;
- `Organic cottn` → proposed alias, not a silent correction;
- blank weight, dense tight group → `GROUPED_MEDIAN` fill with that lineage;
- blank weight, high-spread group → fails dispersion → reference constant;
- implausible weight → trips the plausibility band → rejected/flagged;
- duplicate file upload → idempotent rerun, no duplicate rows.

A ladder branch or anomaly type with no fixture test is a coverage gap.

## Fill-accuracy metric (QA, not method selection)

Because the generator holds ground truth, report the measured error of the
**fixed** rule (e.g. grouped-median weight fill within *X%* MAE on held-out
truth; reference-constant fallback within *Y%*). This is QA of one rule —
measuring it, not selecting among methods by score. Report it; don't gate the
build on a tuned threshold.

## Where tests live and how they run

- `tests/` for cross-module and README/behavior tests; a colocated `test_*.py`
  next to a module is fine for a unit close to its code.
- `pyproject.toml` runs unit tests + module doctests (`--doctest-modules`);
  `tests/test_readme.py` runs the README doctests.
- Run: `uv run pytest`. Keep the suite green before every commit
  (`carbonara-voice` / CLAUDE.md say when to commit).
