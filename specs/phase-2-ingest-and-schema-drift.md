# Phase 2 — Ingest + schema-drift gate

Branch `phase-2-ingest-and-schema-drift`. Implements milestone M2 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, per §7.2.

## Objective

Safely admit one source file: detect its format, store its bytes immutably,
content-hash it, register it idempotently, and profile its schema. Halt before
any unsafe processing when the schema drifts from the last accepted one, emitting
a deterministic mapping-review proposal. No normalization, no per-cell work, no
canonical records yet — this phase only decides *whether* a file may proceed and,
if not, *what mapping* a reviewer should confirm.

## Deliverables

```text
carbonara/profile.py       tabular profile: columns, coarse type, null rate, cardinality, samples
carbonara/source_schema.py expected source schema + alias table + drift diff + mapping proposal
carbonara/ingest.py        detect, hash, store bytes, register (idempotent), profile, gate → IngestResult
tests/test_profile.py      profile shape + determinism + coarse type inference
tests/test_source_schema.py drift diff (add/remove/rename/type-change) + deterministic proposal
tests/test_ingest.py       clean accept, drift halt, duplicate no-op, store immutability
```

All three modules live in `carbonara/`, so the determinism guard applies: no
wall-clock, no randomness, no `uuid4`, no env reads. Content addressing supplies
the only identity this phase needs (the sha256), and it is a pure function of the
bytes.

## The mechanism

Admitting a file is one flow with three concerns, kept in three modules:

1. **Profile** (`profile.py`) — read the tabular file into a `Profile`: the
   column names in order, and per column a coarse type, null rate, cardinality,
   and a small sorted sample. Deterministic: same bytes ⇒ same profile.
2. **Schema** (`source_schema.py`) — the versioned `EXPECTED_SOURCE_SCHEMA`
   (the raw vendor file's known shape), a deterministic alias table, and the pure
   functions that diff a profile against an accepted schema and propose a mapping.
3. **Ingest** (`ingest.py`) — orchestration: detect format, hash bytes, store the
   original, register (or short-circuit as a duplicate), profile, run the drift
   gate, and return an `IngestResult`.

### Detection and the byte store

- **Detect** CSV vs XLSX by content, not by extension: an XLSX is a zip
  (`PK\x03\x04` magic); anything else decodable as text is treated as CSV. The
  extension is a hint only.
- **Store** the original bytes verbatim under a content-addressed path
  (`raw/<sha256>.<ext>`); inputs are immutable and never rewritten (brief §8.3).
- **Content-hash** is `sha256` of the raw bytes — the file's identity and the key
  for idempotency.

The store root is an injected path (tests use a tmp dir); nothing is written
outside it, and no timestamp is recorded (the ledger's `created_at` arrives in
Phase 4, where it will be injected, not read from the clock).

### Registration and idempotency

A small `registry.json` maps content hash → `{filename, format, schema_status}`,
written with sorted keys so it is byte-stable. On `admit`:

- **New hash:** store bytes, register, profile, gate.
- **Known hash, `rerun=False`:** no-op — return `IngestStatus.DUPLICATE`, write
  nothing. This is the §12 "duplicate file upload → idempotent rerun, no
  duplicate rows" case.
- **Known hash, `rerun=True`:** re-process without duplicating stored bytes.

Idempotency keys on the content hash, not the filename: the same bytes under a
new name are still a duplicate (`fix(ingest)` house example — reject by hash, not
filename).

### The schema-drift gate

The baseline is the **last accepted schema** if one exists, else the versioned
`EXPECTED_SOURCE_SCHEMA`. `diff_schema(profile, baseline)` reports, per the
brief's four triggers:

| Trigger | Detected as |
|---|---|
| Added column | present in profile, absent in baseline |
| Removed column | present in baseline, absent in profile |
| Renamed column | one added + one removed that alias or fuzzy-match |
| Type change | shared column whose coarse type differs |

Any trigger ⇒ **stop**, `IngestStatus.REVIEW_REQUIRED`, and a mapping proposal.
A clean match ⇒ `IngestStatus.ACCEPTED`, and the profile's schema is recorded as
the new accepted baseline.

Column **names and order** are the hard contract. Coarse type is compared
tolerantly: `EXPECTED_SOURCE_SCHEMA` declares the type the *raw* file actually
carries (weights arrive as free text with units, dates arrive malformed — those
columns are `string` at ingest), so ordinary messiness does not trip the gate.
Per-cell normalization and anomaly flagging are Phase 3, deliberately not here.

### The mapping proposal — deterministic, aliases first

For each unmatched profile column, `propose_mapping` proposes a target from the
unmatched baseline columns:

1. **Known alias** first — a fixed table (e.g. `vendor → supplier`), the
   deterministic, citable mapping.
2. **Bounded fuzzy match** otherwise — `difflib.SequenceMatcher` ratio above a
   fixed threshold (stdlib, no new dependency); ties broken by baseline column
   order so the result is reproducible.
3. **No match** — reported as an added column with no proposal; removed baseline
   columns are reported for the reviewer, never auto-filled.

Nothing is corrected silently: `Organic cottn` and a renamed header both surface
as *proposals*, not edits (brief §7.2, §12).

## Why the shipped fixture trips the gate

`fixtures/bom_v1.csv` renames `supplier → vendor` (`RENAMED_HEADERS` in the
generator). Its first import therefore diffs against `EXPECTED_SOURCE_SCHEMA`,
finds one removed (`supplier`) + one added (`vendor`) that the alias table pairs,
and halts `REVIEW_REQUIRED` proposing `vendor → supplier`. This is the §12
"renamed header → schema-drift warning, review required" case, exercised on the
real artifact rather than a hand-built one. The clean-import test constructs a
schema-matching file (the same rows under the expected header) to prove the
accept path.

## Scope boundaries (deliberately out of scope)

- **XLSX parsing.** The gate *detects* XLSX by magic bytes, but this phase parses
  only CSV (stdlib `csv`); an XLSX input raises a clear unsupported-format error.
  No XLSX fixture exists and the M2 exit gate is CSV-only; adding an `openpyxl`
  dependency for an unexercised path would be speculative (brief §2, reuse-first).
- **Normalization, anomalies, fills.** Phases 3–4. Phase 2 does not touch cell
  values or emit `CanonicalRecord`s.
- **Review-queue persistence / approval history.** Phase 3's review queue owns
  approve/reject and turning approvals into rules. Phase 2 emits the proposal;
  it does not store a decision.

## Ordered steps (one commit each)

1. **Spec** — this file.
2. **Profile.** `carbonara/profile.py`: `Profile` frozen dataclass and
   `profile_table`, with coarse-type inference (`empty < integer < float < date <
   string`, all-non-blank-parse rule) and sorted samples. Doctest + unit tests.
3. **Schema + drift.** `carbonara/source_schema.py`: `EXPECTED_SOURCE_SCHEMA`,
   the alias table, `SchemaDiff`, `diff_schema`, and `propose_mapping`. Doctest +
   unit tests over all four triggers and the proposal ordering.
4. **Ingest.** `carbonara/ingest.py`: format detection, sha256, byte store,
   `registry.json`, idempotency, orchestration, and the `IngestResult` /
   `IngestStatus` types. Unit tests: clean accept, drift halt, duplicate no-op,
   store immutability.
5. **§12 fixture-behavior tests.** `tests/test_ingest.py` against the real
   `fixtures/bom_v1.csv`: renamed-header drift halts with the `vendor → supplier`
   proposal; re-admitting identical bytes is a no-op.

## Exit gate (brief §16)

- A clean file imports (`ACCEPTED`, schema recorded).
- A changed-schema file halts (`REVIEW_REQUIRED`) with a mapping proposal.
- Re-uploading the same bytes is a no-op (`DUPLICATE`, no new rows/files).
- The §12 renamed-header and duplicate-file fixtures pass.
- `uv run pytest` and `uv run pre-commit run --all-files` are green; re-running an
  unchanged import yields an identical registry and profile.
