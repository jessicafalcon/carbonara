# Phase 8 — Demo + limitations note, review loop applied

Branch `phase-8-applied-review-loop`. Implements milestone M8 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16: make the story repeatable in five
minutes, with the review loop applied end to end. Gated on Phase 7 landing
(merged, PR #8). Draws the chaining from §8.1 (Bloodline spine) and §8.2 (the
ledger), the review loop from §10, the claims boundaries from §15, and the
library boundaries from §11.

## Objective

Two pieces:

1. **Apply the review loop.** Wire `review.approved_rules()` back into the
   pipeline as a deterministic second pass. An approved mapping
   (`Organic cottn` → `organic cotton`) is *re-applied to the cell it corrects*,
   not merely minted. The re-apply chains its lineage onto the cell's original
   source with `carbonara.augment.augment_lineage` (normalize → approved alias)
   instead of clobbering it (§8.1), and writes a ledger event like any rule
   (§8.2). This is the first genuine two-rule cell in the live pipeline — where
   the Phase 7 helper meets real data.
2. **The five-minute story.** A scripted, deterministic walkthrough (upload →
   drift gate → review → approve → re-run → fill → footprint → provenance trace)
   that shows a chained two-entry lineage in the provenance drawer; a short
   limitations note (§15); a README with tested doctests.

## Decisions (confirmed before build)

- **Injection point and pipeline slot.** The approval decision (actor / status /
  `at`) is constructed *outside* `carbonara/` — in the demo script — and passed
  in as an explicit `approvals` parameter on `pipeline.run()`, the same shape as
  the already-injected `created_at`. No clock, no env read; the second pass stays
  byte-identical and passes the determinism guard. The pass slots in **right
  after `normalize_records`**, so the corrected material flows into `fill_weights`
  and `compute_footprint` (the three `Organic cottn` cells go from unresolved /
  not-costed to costed).
- **Scope: broader.** Beyond the minimal re-apply + chain + ledger event, this
  phase also (a) persists and replays review decisions, so the demo loads
  approvals from an in-repo fixture rather than constructing them inline, and (b)
  reflects the applied loop in the brand-facing view (§10). Two bounded cuts,
  recorded here so scope does not drift:
  - **Generalization is keyed to `proposed_value`, not to inventing per-category
    semantics.** `approved_rules()` today mints only from `MAPPING`. It is
    generalized to mint from *any approved finding that carries a
    `proposed_value` and a target `column`* — which is the honest boundary of
    "a value a reviewer approved." Categories with no `proposed_value` (a bare
    `VALIDITY` or `COMPLETENESS` flag) mint nothing; approving them stays a
    recorded decision with no rule to re-apply. We do not fabricate a corrected
    value where the finding proposes none (§15).
  - **The view stays static HTML.** "Live approve/re-run" means the rendered view
    reflects the *applied* approval — the drawer shows the chained two-entry
    lineage and the queue shows the approved status — not an in-browser server
    round-trip. Consistent with the Phase 5 static-HTML medium.
- **Demo medium.** A deterministic `scripts/demo.py` walkthrough plus a README
  `Walkthrough` section with tested doctests; the limitations note is a README
  `Limitations` section citing §15 (one document, executed by `test_readme`), not
  a separate file.

## Design — the second pass

### Where the decision enters, and the two-entry lineage

The `Organic cottn` cell has *no* original Bloodline source today: normalize
raises a proposal `Finding` and leaves `material_normalized` null and unsourced
(§12 — a near-miss is never applied silently). So "chain onto the original
source" needs an original to chain onto. The re-apply constructs the honest two
entries the brief names:

1. **normalize (original).** The deterministic lowercasing normalize applies to
   every material — `"Organic cottn"` → `"organic cottn"` — emitted as a
   `NORMALIZE_MATERIAL` `RuleEvent`. This is the form the reviewer saw. It seeds
   the cell's head `Source` through the existing `apply_lineage`.
2. **approved alias (approval).** The reviewer-approved resolution
   `"organic cottn"` → `"organic cotton"`, emitted as a `REFERENCE_RESOLVE`
   `RuleEvent` whose `method_params` carry the injected decision (actor, status,
   `at`) and confidence. This chains onto the head via `augment_lineage`.

Result: `material_normalized = "organic cotton"`, two ledger rows, and a
two-entry `lineage` list in the spine — exactly the shape `augment.py`'s own
doctest demonstrates (`normalize_material` → `reference_resolve`).

### `carbonara/apply_review.py` (new, deterministic — in the data path)

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class AppliedApproval:
    rule: ApprovedRule  # from review.approved_rules()
    decision: ReviewDecision  # injected actor / status / at


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplyResult:
    records: list[SourceRecord]
    events: list[RuleEvent]  # base normalize + approval, for the ledger
    chains: list[LineageChain]  # (record_id, column, RuleRecord) for augment_lineage


def apply_approvals(records: list[SourceRecord], approvals: Sequence[AppliedApproval]) -> ApplyResult:
    """Re-apply approved rules to the cells they correct, chaining lineage."""
```

For each approval, match the records it corrects (a `MAPPING` alias matches every
record whose raw material equals `rule.key` and whose target column is still
unresolved), set the corrected value, and emit the two events plus the chain
record. Records are matched in `record_id` order; `approvals` are applied in a
sorted, stable order — byte-identical across runs. Empty `approvals` is a no-op
that returns the records unchanged, so the existing single-pass behaviour is
preserved exactly.

### Pipeline wiring (`pipeline.run`)

```text
normalize_records
  → apply_approvals(records, approvals)     # NEW — corrects cells, emits events + chains
  → fill_weights                            # now fills/keeps the corrected material
  → compute_footprint                       # now costs the three corrected cells
  → to_frame → apply_lineage(base events)   # seeds the normalize head source
  → augment_approval_lineage(frame, chains) # chains the approval → two-entry lineage
```

Approval events join `normalized.events` so the ledger records them under the
run. The base normalize event goes through `apply_lineage` (seeds the head); the
approval is applied *after*, per chain, through `augment_lineage` so it appends
rather than clobbers. `run()` gains one keyword-only parameter,
`approvals: Sequence[AppliedApproval] = ()`; every existing caller is unchanged.

## Design — persisted review decisions

A small deterministic serialization on `ReviewQueue` (or a `ReviewLog` helper):
decisions round-trip through JSON lines — `finding_id`, `status`, `actor`,
`note`, `at` — in queue order, no clock. The demo loads its approval from an
in-repo fixture (`fixtures/review_decisions.jsonl`) and replays it onto the
findings, so the walkthrough is reproducible from a clean checkout without
constructing decisions inline. Replay is exact: same file ⇒ same decisions ⇒ same
`approved_rules()`.

## Design — the walkthrough and the view

- **`scripts/demo.py`** (outside `carbonara/`, file I/O and a fixed injected
  clock allowed): narrates the eight steps over `fixtures/bom_v1.csv`, using a
  `tempfile` store for the drift-gate step, injecting `created_at` and the replayed
  approval. It prints the run twice — before approval (the cell is an unresolved
  proposal, not costed) and after (costed, with the two-entry chain) — and dumps
  the provenance trace for one corrected record so the chain is visible.
- **`carbonara/view.py`**: the provenance drawer reads each corrected cell's
  `lineage_history` from the spine and renders the ordered chain; the review queue
  row shows the approved status. The render stays deterministic and static.

## Deliberately out of scope

- **A review UI or server.** Approvals enter as data (a fixture + an injected
  decision); there is no interactive queue, no write-back endpoint.
- **Per-category correction semantics.** Findings without a `proposed_value` mint
  no rule (§15); we do not guess a corrected value.
- **New provenance stores.** The chain rides the existing `data_lineage` spine
  (Phase 7 helper) and the ledger; no parallel history.
- **Re-running the whole catalog through approvals.** The demo proves the loop on
  the planted `Organic cottn` cells (§6/§12); a bulk approval workflow is not a
  §16 gate.

## Ordered steps (one commit each)

1. **Spec** — this file, and mark Phase 7 merged (PR #8) in the CLAUDE.md Current
   status.
2. **Generalize `approved_rules`.** `review.py`: mint a rule from any approved
   finding carrying a `proposed_value` + `column`, keeping the reusable-alias
   semantics for `MAPPING`; a category without a proposed value mints nothing.
   Tests cover the generalization and the no-value case.
3. **Persist review decisions.** `review.py`: deterministic JSONL serialize /
   replay of decisions; `fixtures/review_decisions.jsonl`; tests for exact
   round-trip.
4. **Second-pass module.** `carbonara/apply_review.py`: `AppliedApproval`,
   `apply_approvals`, the base-normalize + approval events, and the chain records,
   with a module doctest on the `Organic cottn` cell. Passes the determinism
   guard; empty approvals is a no-op.
5. **Wire into the pipeline.** `pipeline.run`: `approvals` parameter; apply after
   normalize; approval events into the ledger; seed via `apply_lineage`, chain via
   `augment_lineage`. Tests: byte-identical re-run; the approved cell carries a
   two-entry lineage; the three cells are now costed; empty approvals reproduces
   the current output exactly.
6. **Reflect it in the view.** `view.py` + `scripts/build_view.py`: the drawer
   renders the chained lineage; the queue shows approved status; the view build
   passes the replayed approval. Tests updated.
7. **Scripted walkthrough.** `scripts/demo.py`: the deterministic eight-step
   story, before/after, printing the two-entry chain.
8. **README + limitations + status.** A `Walkthrough` section (doctested) and a
   `Limitations` section citing §15; update the CLAUDE.md Current status to the
   exit gate.

## Exit gate (brief §16)

- The five-minute walkthrough is reproducible from a clean checkout (offline,
  deterministic; `scripts/demo.py` runs and its README doctests pass).
- An approved mapping re-applies and its cell carries a two-entry lineage
  (original + approval), visible in the provenance drawer.
- The re-apply chains via `augment_lineage` (not clobber) and writes a ledger
  event; the pipeline output, ledger, and lineage are byte-identical on a re-run.
- `uv run pytest` (unit + doctest + README) and `uv run pre-commit run
  --all-files` are green.
- README claims stay inside the §15 boundaries.
