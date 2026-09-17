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
