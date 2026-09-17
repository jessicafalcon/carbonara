# feat — wire the anomaly net into the pipeline

Branch `feat/wire-anomaly-net`, off `main` after the audit follow-ups (PR #10).
Closes the gap the resilience review found: `carbonara/anomalies.py`
`detect_anomalies` — validity, completeness, duplicate-key, cross-field,
distribution — is called **only from tests**. `pipeline.run` assembles findings
from normalize + fill + footprint alone, so on the fixture the live pipeline
surfaces 7 findings while `detect_anomalies` would add ~119 more. The planted
anomalies (negative quantity, malformed date, duplicate key, composition ≠ 100%,
extreme weight/price) are computed by tested code but never reach the pipeline
output or the brand-facing view — the opposite of the brief's "flag, don't
silently fix" boundary (§7.3, §10, §15).

## Objective

Surface every detected anomaly as a reviewable finding in `pipeline.run`, make
the view legible with that many findings, and prove the §12 fixture-behavior
cases end to end through `run()` — not only through `detect_anomalies` in
isolation. No new detector; wire the one that exists.

## Design decisions

- **Detect on the pre-fill records.** Run `detect_anomalies` on `applied.records`
  (post-approval, pre-fill). Completeness ("missing weight") must fire on the
  cell as it arrived, before the ladder fills it — a filled weight is an estimate,
  and the finding is the honest record that it was absent. `detect_anomalies`
  reads none of the material-mapping columns approvals touch, so pre- vs
  post-approval is identical for its purposes; `applied.records` is the pipeline's
  canonical pre-fill set.
- **Additive, deterministic, no id collisions.** `Finding.finding_id` is
  `record_id:column:category` — content-derived, no counter or clock. The anomaly
  categories (validity/completeness/duplicate_key/cross_field/distribution) are
  disjoint from the existing MAPPING/PLAUSIBILITY findings, so merging cannot
  collide. `detect_anomalies` already emits in a fixed order, so the run stays
  byte-reproducible (guard-clean — no data-path change beyond a call).
- **Weight completeness is residual, not raw.** Flagging every originally-missing
  weight floods the queue with cells the ladder resolves (97 of 123 on the
  fixture, all filled) and buries the actionable findings — while the weights the
  ladder *cannot* resolve raised no finding at all (`fill.py` set
  `ACTION_REQUIRED` silently). So weight completeness is owned by the fill stage:
  it flags only the residual null the ladder leaves (§7.4 tier 5, MEDIUM), the
  gap that actually needs a decision. `detect_anomalies` keeps country
  completeness (no ladder resolves country). The "was imputed" fact is still
  carried by the observed/filled share, the per-cell fill lineage, and the
  `no weight` coverage tag — it does not need a queue item. (Decision taken
  mid-branch after the review showed the queue was 79% non-actionable.)
- **View: summarize, do not hide.** The review queue lists all findings, already
  sorted HIGH → LOW. Add a by-severity summary to the readiness panel (§10) so a
  reviewer sees `high/medium/low` counts at a glance instead of scrolling. Nothing
  is capped or collapsed — capping would hide data, against the thesis.
- **Carry the deferred view caption.** Label the footprint headline as a
  material-stage estimate in the view (the prose landed in PR #10; the shipped
  artifact still lacks it).

## Steps (one commit each, green before the next)

1. **Spec** — this file.
2. **Wire it in.** Call `detect_anomalies(applied.records)` in `pipeline.run`;
   fold its findings into `PipelineResult.findings` after `normalized.findings`.
   Update the `run` docstring. Test (`test_pipeline`): the run now surfaces each
   anomaly category, a re-run reproduces the findings, and empty input is empty.
3. **Prove §12 end to end.** In `test_normalize_anomaly_fixtures` (or a focused
   pipeline test), assert the planted cases surface through `run()` — negative
   quantity (validity, high), zero-weight-on-positive-value (cross-field, high),
   duplicate key, composition ≠ 100%, extreme weight (distribution). This is the
   integration the isolated `detect_anomalies` tests never covered.
4. **View.** Add the by-severity summary to the readiness panel and the
   material-stage caption under the headline. Extend `test_view` to assert both
   render and that a high-severity anomaly reaches the queue.
5. **Demo.** Update the narrated step 3 to report the honest breakdown
   (`N findings · 6 mappings + M anomalies`) without losing the mapping focus;
   keep `test_demo` green (determinism + the asserted lines).
6. **Status + PR.** Update CLAUDE.md Current status; push; open the PR
   (`carbonara-pr` + `carbonara-voice`). Stop before merge.

## Determinism

No clock, no randomness, no env read added — one function call whose output is a
fixed-order list keyed on content. The re-run reproducibility tests
(`render_view(a) == render_view(b)`, identical records/events/ledger) must stay
green; `run_id` is unaffected (it keys on content hash + versions, not findings).

## Deliberately out of scope

- New anomaly detectors or new categories — wire the existing net only.
- Review-queue pagination / grouping UI beyond the severity summary.
- Approving anomaly findings into rules — Phase 8 generalized approvals to any
  finding with a `proposed_value`; anomalies carry none, so they stay reviewable
  and unapplied. No change here.
- Input-boundary hardening (KeyError/UnicodeDecodeError on malformed input) — its
  own branch.

## Exit gate

- `pipeline.run` surfaces the anomaly findings; the §12 planted cases are proven
  through `run()`, not only `detect_anomalies`.
- The view renders the by-severity summary and the material-stage caption; the
  review-queue count reflects the full set.
- A re-run is byte-identical (records, events, ledger, HTML); empty approvals and
  empty input behave as before.
- `uv run pytest` and `uv run pre-commit run --all-files` green.
