# carbonara

A lean connector that turns a messy supplier BOM into an auditable,
component-level carbon estimate — and can prove where every number came from.

It ingests one messy apparel BOM / catalog / purchase-order file, detects schema
drift, normalizes and validates the data through explicit versioned rules, fills
gaps through a deterministic ladder, computes a component-level footprint, and
lets a reviewer trace any number back to the rule that produced it and the source
row it came from.

Every value the pipeline touches is the product of one **versioned,
deterministic rule** that leaves a record. Nothing is silently corrected,
nothing is randomly guessed, and no step depends on an LLM at runtime — the same
input and rule versions always produce byte-identical output, lineage, and
ledger.

See [PROJECT-BRIEF.md](PROJECT-BRIEF.md) for the full design and the phased build
plan.

## Status

The pipeline runs end to end: ingest and schema-drift gate, normalize and
validate, the gap-fill ladder with dual-store provenance, and the
component-level footprint with a brand-facing view and a per-number provenance
drawer. The stretch work is built too: a two-vintage change explanation — a
DuckDB SQL DAG that rolls the footprint up to a production-weighted catalog total
and an icanexplain decomposition of the v1→v2 change — lives in `analytics/`,
outside the connector (see the brief).

```python
>>> import carbonara
>>> carbonara.__version__
'0.1.0'

```

## Footprint

The footprint costs each component by `component_weight_kg × factor(material)`,
using versioned Ecobalyse/ADEME emission factors. Each estimate is a derived
value with its own ledger event and Bloodline source, so it traces back to the
rules, the source row, and the factor version.

```python
>>> from carbonara.contract import CanonicalRecord
>>> from carbonara.materialize import SourceRecord
>>> from carbonara.footprint import compute_footprint
>>> rec = CanonicalRecord(
...     record_id="r0001", source_row_id="1", style_id="TSH-1", sku="S",
...     component="shell fabric", material_raw="cotton",
...     material_normalized="cotton", component_weight_g=200.0, supplier_raw="Acme",
... )
>>> [component] = compute_footprint([SourceRecord(record=rec, raw={})], []).components
>>> round(component.estimated_kgco2e, 2)  # 0.2 kg × 3.4151 kgCO₂e/kg
0.68

```

Render the view over the fixture BOM to a standalone HTML file:

```sh
uv run python scripts/build_view.py   # writes build/view.html
```

## Change explanation (v1 → v2)

Two BOM vintages (2024 and 2025) differ in planted ways — production volume, a
material-mix shift, and one emission-factor revision. A tiny DuckDB SQL DAG rolls
each vintage up to a production-weighted catalog total `F = Σ mass_kg × factor`,
and icanexplain decomposes the change into an **intensity** effect (the factor
revision) and a **volume/mix** effect (production mass and its material mix). The
two contributions reconcile to the observed change, and the intensity effect
lands on the one material whose factor moved:

```python
>>> from analytics.mart import footprint_mart
>>> from analytics.explain import decompose
>>> change = decompose(footprint_mart())
>>> change.reconciles()  # intensity + volume/mix == observed ΔF
True
>>> round(change.intensity_effect + change.volume_mix_effect - change.observed_delta, 6)
0.0
>>> by_material = change.by_material.set_index("material")["intensity_effect"]
>>> [m for m in by_material.index if abs(by_material[m]) > 1e-6]
['polyester']

```

Build the reconciled explanation as an artifact:

```sh
uv run python scripts/build_explanation.py   # writes build/explanation.json
```

## Cell lineage lifecycle

The Bloodline spine records one source per cell — the *current* value's origin —
so a later rule replaces the earlier one. When a cell is touched by more than one
rule, `carbonara.augment` keeps the whole ordered lifecycle inline: the head
source stays the latest rule (every Bloodline read still works), and the prior
rules ride in its metadata as an oldest-first list, each with its id, version,
and confidence. It is the append-only counterpart to the fill-ladder lineage; the
per-cell list is a projection, not a second copy of the cross-cell ledger.

```python
>>> import bloodline as bl
>>> from carbonara.augment import RuleRecord, augment_source, lineage_history
>>> # A material cell first normalized, then resolved against the reference list.
>>> normalized = bl.Source(
...     source_type="normalize_material",
...     source_metadata={"rule_id": "material_lower", "rule_version": "v1"},
... )
>>> resolved = RuleRecord(
...     rule_id="material_resolve", rule_version="v1",
...     source_type="reference_resolve", confidence=0.9,
... )
>>> head = augment_source(normalized, resolved)
>>> head.source_type  # the head is the latest rule
'reference_resolve'
>>> [r["source_type"] for r in lineage_history(head)]
['normalize_material', 'reference_resolve']

```

## Walkthrough — the review loop, applied

An uncertain mapping is surfaced for review, never auto-applied. When a reviewer
approves it, the approval is re-applied to the cell it corrects as a deterministic
second pass: the approved alias chains onto the cell's normalize source
(`normalize_material → reference_resolve`) instead of overwriting it, and writes a
ledger event like any rule. The decision (actor, status, timestamp) is injected, so
the re-run stays byte-identical.

```python
>>> from carbonara.pipeline import run
>>> from carbonara.review import ReviewQueue
>>> from carbonara.apply_review import applications_from
>>> from carbonara.augment import lineage_history
>>> rows = [{"source_row_id": "65", "style_id": "TSH-11", "sku": "TSH-11-WHT-XS",
...          "component": "shell fabric", "material": "Organic cottn", "composition": "100% cotton",
...          "net_weight": "131 g", "vendor": "Acme Textiles", "country": "Portugal",
...          "order_date": "2024-10-16", "quantity": "3400", "unit_price": "6.26"}]
>>> ctx = dict(content_hash="demo", created_at="2026-01-01T00:00:00Z")
>>> before = run(rows, {"vendor": "supplier"}, **ctx)
>>> before.frame["material_normalized"][0] is None  # 'Organic cottn' is proposed, not applied
True
>>> queue = ReviewQueue(before.findings)
>>> mapping = next(f for f in before.findings if f.category.value == "mapping")
>>> _ = queue.approve(mapping.finding_id, actor="reviewer", at="2026-01-01T00:00:00Z")
>>> after = run(rows, {"vendor": "supplier"}, approvals=applications_from(queue), **ctx)
>>> after.frame["material_normalized"][0]  # the approved alias is re-applied
'organic cotton'
>>> cell = after.frame["data_lineage"][0]["material_normalized"]
>>> [e["source_type"] for e in lineage_history(cell)]  # original + approval, chained
['normalize_material', 'reference_resolve']

```

Run the full narrated story (upload → drift gate → review → approve → re-run →
fill → footprint → provenance trace) over the fixture BOM:

```sh
uv run python scripts/demo.py
```

## Limitations

The connector is deliberate about what it asserts and what it does not (brief §15):

- A filled or approved value is a labeled estimate, never exact. Imputed weights
  carry an uncertainty range; an approved mapping is a recorded reviewer decision,
  not ground truth. Fill accuracy is *measured* against planted ground truth, never
  claimed.
- A footprint that rests materially on filled inputs is reported with its coverage
  and factor assumptions, not as a precise figure.
- An anomaly is not an error until a reviewer decides. Uncertain mappings are
  surfaced for review and applied only through a versioned, approved rule — never
  guessed, never silently corrected.
- Emission factors are external reference data (Ecobalyse / ADEME Base Empreinte),
  versioned in-repo and cited per row; an estimate is only as current as the factor
  table it names.
- Scope is one file at a time — an apparel BOM / catalog / PO in CSV, offline. No
  identity resolution across sources, and no network in the data path.

## Install

```sh
pip install carbonara
```

## Local development

```sh
git clone https://github.com/carbonara/carbonara
cd carbonara && uv sync

# Check code quality
pre-commit install --hook-type pre-push
pre-commit run --all-files

# Run tests (unit + doctests, including this README)
uv run pytest
```

## License

Apache-2.0.
