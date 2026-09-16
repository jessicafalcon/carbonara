---
name: carbonara-correctness
description: >
  What makes a change correct and safe in the carbonara BOM connector — the
  non-negotiable invariants (determinism, provenance, no silent edits, versioned
  rules), general best practices (validation at boundaries, error handling, no
  magic numbers), and a review checklist tuned for Opus 4.8. Read this BEFORE
  landing any change to the data path, when adding a rule, and when reviewing
  code. Pairs with carbonara-craft (how it's written).
---

# carbonara-correctness

Correctness here is stricter than "it runs." The whole product promise is that
every number is reproducible and traceable. A change that computes the right
value but leaves no provenance, or that a second run can't reproduce, is a
**defect**, not a shortcut.

## The four invariants (a change that breaks any of these does not land)

### 1. Determinism

Same input + same rule versions ⇒ **byte-identical** output, lineage, and
ledger. In the data path (`carbonara/`), that means:

- **No LLM at runtime.** No `openai`, `anthropic`, or any model call in `carbonara/`. AI is a build-time tool only.
- **No unseeded randomness.** No `random.*` / `numpy.random.*` without a fixed seed; fixtures seed with `random.seed(42)`.
- **No wall-clock or environment reads.** No `datetime.now()`, `date.today()`, `time.time()`, `uuid.uuid4()`, `os.environ`, or unordered iteration that leaks into output. Timestamps that must be recorded (e.g. ledger `created_at`) are injected as an explicit parameter, not read from the clock inside the rule.
- Deterministic ordering: sort before you serialize; don't rely on dict/set iteration order for output.

The `determinism-guard` hook flags these on every edit. If the guard fires on
intentional build-time code (a generator script *outside* `carbonara/`), that's
expected — keep non-deterministic helpers out of the connector package.

### 2. Every transformation is a versioned Data Augmentation Rule

Normalization and imputation are the *same object*: a rule with a `rule_id` and
`rule_version` that takes inputs, applies a fixed transform, and writes a record.
No value in the output frame changes without one. Bumping behavior means bumping
`rule_version` — never silently altering an existing rule's output.

### 3. Dual provenance on every touched cell

Each rule application writes **both**:

- a Bloodline `Source` on the cell (`source_type` per ladder tier — `DERIVED_FORMULA`, `REFERENCE_RESOLVE`, `GROUPED_MEDIAN`, `REFERENCE_CONSTANT`, `NORMALIZE_<kind>`, `UNKNOWN`), and
- an append-only **ledger** row (`event_id, run_id, record_id, column, rule_id, rule_version, source_type, method_params, value_before, value_after, is_original_null, uncertainty_range, created_at`).

Raw inputs are immutable and content-hashed; transforms are additive; the raw
value+unit is preserved beside every normalized value. A filled value carries an
**uncertainty range**, never a bare point estimate.

### 4. No silent edits

Anomalies, uncertain mappings, and implausible values become **reviewable
events**, not corrections. The pipeline flags; a human (or a versioned, approved
rule) decides. Refusing to compute a statistic below the support/dispersion bar
is a *stated design decision*, surfaced as `action required`, not a quiet guess.

## General best practices (baseline, everywhere)

- **Validate at trust boundaries.** File ingest, external API responses (Ecobalyse, Open Supply Hub), and any parsed field are validated before use — explicit checks, clear errors. Never trust a header, a unit, or a composition string.
- **Error handling that can't lose data.** Raw bytes are stored before parsing; a parse failure produces a flagged event, not a dropped row. Fail loud on programmer error, fail *recorded* on data error.
- **No magic numbers.** Support `N`, back-off levels, dispersion cutoff `c`, plausibility band — all named, versioned config ([§7.6](../../../PROJECT-BRIEF.md)).
- **Idempotency.** Re-importing the same bytes is a no-op; re-running unchanged inputs reproduces everything. External calls are cached (see `carbonara-efficiency`).
- **External data is a suggestion until verified.** A fuzzy supplier match or an OSH lookup is proposed, never asserted as fact.

## Review checklist (Opus 4.8 tuned)

When reviewing (or self-reviewing before landing), **the finding stage is about
coverage, not filtering.** Report every issue you find — including low-severity
or uncertain ones — with a confidence level and estimated severity, so ranking
happens as a separate step. It is better to surface a finding that later gets
dropped than to silently miss a real bug. Only omit pure style/naming nits that
ruff already governs.

Check, in order:

1. **Invariants** — determinism, versioned rule, dual provenance, no silent edit (above). These are correctness bugs, not nits.
2. **Ladder routing** — does each missing cell hit the correct tier, first-match-wins, with support/dispersion/plausibility guards enforced and the fall-through path exercised?
3. **Boundary handling** — blank vs. zero, mixed units, malformed dates, duplicate keys, composition ≠ 100%, negative quantity, extreme price/weight. Each should route to the specified event.
4. **Reproducibility** — will a second run produce identical output/lineage/ledger? Any ordering, clock, or randomness leak?
5. **The check** — is there a runnable test/doctest that fails if this logic breaks? Does a planted fixture cover it?
6. **Over-engineering** — anything to delete, inline, or replace with stdlib/Bloodline? A single implementation behind an interface? Speculative config? (Route this like any other finding.)

State scope explicitly when a fix applies broadly (e.g. "apply this guard to
every ladder tier, not just grouped-median"). Fix bugs at the root — one guard
in the shared rule, not one per caller.
