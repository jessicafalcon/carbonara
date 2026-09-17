# Phase 7 — Bloodline augmentation-rule helper *(aspiration)*

Branch `phase-7-augmentation-rule-helper`. Implements milestone M7 of
[PROJECT-BRIEF.md](../PROJECT-BRIEF.md) §16, closing the source-vs-lifecycle gap
named in §8.1 and the contribution opportunity in §11. Gated on Phase 6 landing
(merged, PR #7).

## Objective

Bloodline stores the source of a cell's *current* value — one `Source` per cell,
and `override=True` replaces it (§8.1, "known limit"). It does not keep the
ordered lifecycle of the rules that produced the value, which is why we carry the
ledger (§8.2). This phase adds a small helper that **preserves a cell's original
lineage while attaching a rule record** (rule id/version, inputs, confidence), so
a single cell carries its lifecycle inline in the spine — without reimplementing
lineage (§11) and without touching the ledger's role.

The deliverable is an in-repo module, written to Bloodline's public surface so it
could be lifted upstream unchanged; no upstream PR is opened here (merge timing is
not ours, §11).

## Design — the lifecycle lives inside the head `Source`

Bloodline's `data_lineage` column holds, per row, `{column → Source}` where each
`Source` is `{source_type, source_metadata}`. We keep that contract exactly: the
cell's **head `Source` stays the latest rule**, so every Bloodline read, merge,
and ER diagram still works. The ordered lifecycle rides in the head's
`source_metadata` under a reserved `"lineage"` key — an oldest-first list of rule
records. `Source.source_metadata` is free-form by design, so this is using
Bloodline as intended, not bolting a parallel store onto it.

```text
data_lineage[column] = {
    "source_type": "reference_resolve",          # the head = latest rule
    "source_metadata": {
        "rule_id": "material_resolve", "rule_version": "v1",
        "lineage": [                              # oldest → newest
            {"rule_id": "material_lower", "rule_version": "v1",
             "source_type": "normalize_material", "inputs": {...}, "confidence": null},
            {"rule_id": "material_resolve", "rule_version": "v1",
             "source_type": "reference_resolve", "inputs": {...}, "confidence": 0.9},
        ],
    },
}
```

The first rule seeds the list; each augmentation appends. A cell that already had
a plain carbonara `Source` (from `carbonara/lineage.py`, one `{rule_id,
rule_version}` payload) is folded in as the list's first entry the first time it
is augmented, so no prior lineage is lost.

### How it maps onto the existing tiers (§8.1) and the ledger (§8.2)

- **Tiers:** each list entry's `source_type` is a `SourceType` value — the same
  ladder tiers already used (`normalize_*`, `reference_resolve`, `grouped_median`,
  …). A cell's list is the ordered sequence of tiers that touched it.
- **Ledger, not duplicated:** the ledger stays the global append-only, cross-cell
  event log (`run_id`, `created_at`, per-event ids). The `"lineage"` list is the
  *projection onto one cell*, inline in the spine, light metadata only — no
  `created_at`, no `run_id`, no event id. A provenance drawer can read one cell's
  lifecycle without joining the whole ledger; the ledger remains the authority on
  ordering across the run. No clock and no id-minting in the helper, so it stays
  in `carbonara/` and passes the determinism guard.

## API (`carbonara/augment.py`)

Depends only on `bloodline`, `pandas`, and stdlib — no `carbonara` imports — so
the module is liftable upstream as-is. The connector-specific tiers appear only in
the example and tests.

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class RuleRecord:
    rule_id: str
    rule_version: str
    source_type: str  # a SourceType value
    inputs: dict[str, object] = {}
    confidence: float | None = None


def augment_source(prior: bl.Source | None, record: RuleRecord) -> bl.Source:
    """Head Source whose source_type is `record`'s and whose metadata carries the
    prior lineage with `record` appended. Seeds the list from `prior` on the first
    call; a None/unsourced prior yields a single-entry list."""


def augment_lineage(frame, *, record: RuleRecord, row_mask, column) -> pd.DataFrame:
    """Attach `record` to a column's masked cells via apply_data_lineage,
    preserving each cell's prior lineage instead of clobbering it. Cells are
    grouped by prior source and applied in sorted order — deterministic."""


def lineage_history(source: bl.Source | dict | None) -> list[dict]:
    """Read a cell's ordered lifecycle back out (oldest first)."""
```

`augment_lineage` reads each masked cell's prior head `Source`, groups masked rows
by that prior (JSON key, sorted), builds one augmented `Source` per group, and
writes it back through `bl.apply_data_lineage(..., override=True)` — one call per
group. Grouping keeps it to Bloodline's public write path; sorting makes the
result byte-identical across runs regardless of row or dict order.

## Delivery target (§11)

In-repo helper, written clean enough to lift upstream. An actual fork + PR to the
Bloodline package is out of scope for this phase; it can be offered later if
wanted, but it is gated on their review and adds no value to the §16 exit gate.

## Deliberately out of scope

- **Rewiring the live pipeline.** `carbonara/lineage.py:apply_lineage` keeps
  clobbering with `override=True` — every existing cell in the connector is
  touched by exactly one rule, so there is no chain to preserve there yet, and
  changing it would churn every determinism snapshot for no gain. The helper is
  demonstrated on a realistic two-rule cell, not forced into the current one-rule
  path.
- **A new store or column.** The lifecycle rides in the existing `data_lineage`
  spine; no parallel history column (§11).
- **Timestamps / event ids per cell.** That is the ledger's job (§8.2); the helper
  stays deterministic and metadata-light.

## Ordered steps (one commit each)

1. **Spec** — this file, and mark Phase 6 merged (PR #7) in the CLAUDE.md Current
   status.
2. **Helper module.** `carbonara/augment.py`: `RuleRecord`, `augment_source`,
   `augment_lineage`, `lineage_history`, with a module doctest drawn from the
   connector (a `material` cell whose lifecycle is `normalize_material` →
   `reference_resolve`, both preserved). Passes the determinism guard; its doctest
   is green.
3. **Regression tests.** `tests/test_augment.py`: first rule seeds the list; a
   second appends oldest→newest; the original entry is preserved, not clobbered;
   the head `source_type` is the latest rule; an unsourced cell seeds a
   single-entry list; only the masked cells and named column change; the result is
   byte-identical across runs and independent of input order; and the helper
   composes on top of the real `carbonara/lineage.py:apply_lineage` output.
4. **Docs + status.** A short "Cell lineage lifecycle" section in the README with a
   doctest example, and update the CLAUDE.md Current status to the exit gate.

## Exit gate (brief §16)

- Regression tests pass (`tests/test_augment.py`) and a documented example runs as
  a doctest (the module doctest and the README section).
- The helper preserves original lineage and attaches a rule record (rule
  id/version, inputs, confidence) inline in the Bloodline spine, using
  `apply_data_lineage` / `Source` as intended — no reimplemented lineage, no
  parallel store.
- Deterministic: the augmented `data_lineage` reproduces byte-for-byte on a re-run.
- The helper lives in `carbonara/` and passes the determinism guard.
- `uv run pytest` and `uv run pre-commit run --all-files` are green.
