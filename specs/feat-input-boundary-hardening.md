# feat — input-boundary hardening

Branch `feat/input-boundary-hardening`, off `main` after the anomaly net (PR #11).
Closes the second half of the resilience audit: `ingest.admit` and
`pipeline.run` assume clean bytes and a complete schema, so the messy input the
connector exists to accept raises raw Python tracebacks instead of a clear,
recorded outcome — a non-UTF-8 vendor file (`UnicodeDecodeError`), a mapping that
drops a required column (`KeyError`), a non-integer `source_row_id` (`ValueError`),
and a header-only file (silently "accepted · 0 kgCO₂e").

## Objective

Turn each **data** error at the file boundary into a graceful, deterministic
outcome — a decoded read, a clear typed error that names the problem, or a
reviewable finding — while leaving genuine **caller** errors (a wrong path) as
the loud, already-clear exceptions they should be. The principle (carbonara-
correctness): fail *recorded* on a data error, fail *loud* on a programmer error.

## Design decisions

- **Encoding: decode with a fallback, and record it.** `_read_csv` tries UTF-8,
  then falls back to CP1252 (Windows-1252 — a superset of Latin-1 that decodes
  any byte, so a real Western vendor export never crashes). The encoding used is
  recorded on `IngestResult` (and the registry entry) as provenance: a file read
  as CP1252 says so. Deterministic — a fixed try order, keyed on the bytes; the
  content hash is unchanged (it is over the raw bytes, not the decoded text).
- **Row schema: a clear typed error, not a raw traceback.** `materialize`
  validates each mapped row before building the record. A missing required source
  column, or a `source_row_id` that is not an integer, raises `SourceSchemaError`
  naming the column / row / offending value. This is a structural contract breach
  — the drift gate is the designed place to catch a missing column
  (`REVIEW_REQUIRED`), so reaching `materialize` with one is a bypass, and the
  right response is a diagnosable failure, not a silent guess. `record_id` keeps
  its `r%04d` form (the whole system — ledger, tests, lineage — relies on it);
  loosening the id scheme is out of scope.
- **Empty source: a finding, not silence.** A header-only file passes the gate
  (schema matches, no rows) and today yields a clean "0 kgCO₂e" indistinguishable
  from a healthy run. `run` surfaces one high-severity validity finding — "source
  has no data rows" — so an empty catalog is visible, not silent.
- **A wrong path stays a loud error.** `admit`/the scripts open a path directly;
  a missing file is a caller error, and `FileNotFoundError` already names the
  path. No change — turning it into a finding would dignify a bug as data.

## Steps (one commit each, green before the next)

1. **Spec** — this file.
2. **Encoding fallback.** `_read_csv` decodes UTF-8 → CP1252; thread the encoding
   onto `IngestResult` and the registry. Tests: a CP1252 file admits and reads,
   the encoding is recorded, an ASCII/UTF-8 file still reads as UTF-8.
3. **Row-schema validation.** `SourceSchemaError` in `materialize` for a missing
   required column and a non-integer `source_row_id`, naming the offender. Tests:
   each raises with a clear message; the happy path is unchanged.
4. **Empty-source finding.** `run` surfaces the "no data rows" finding on empty
   input; update the empty-input expectation. Test: a header-only run carries the
   finding and still produces a valid (zero) footprint.
5. **Status + PR.** Update CLAUDE.md; push; open the PR. Stop before merge.

## Determinism

No clock, randomness, or env read: the encoding fallback is a fixed try order,
the typed errors are pure functions of the row, and the empty finding is keyed on
row count. Re-run reproducibility is unaffected; `content_hash` and `run_id` are
unchanged.

## Deliberately out of scope

- Missing-file handling — a caller error; `FileNotFoundError` is already clear.
- XLSX parsing — still a typed `UnsupportedFormatError` (this phase is CSV).
- Loosening `record_id` away from `r%04d`.
- Encodings beyond UTF-8 / CP1252 (e.g. UTF-16, Shift-JIS) — CP1252 covers the
  Western vendor files in scope; a broader charset detector is not warranted.

## Exit gate

- A CP1252 file admits and reads (no crash); the encoding is recorded.
- A missing required column and a non-integer `source_row_id` raise
  `SourceSchemaError` with a message that names the problem, not a raw
  `KeyError`/`ValueError`.
- A header-only file surfaces the "no data rows" finding.
- `uv run pytest` and `uv run pre-commit run --all-files` green; re-run is
  byte-identical.
