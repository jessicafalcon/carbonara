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
drawer. Stretch work (Lea, icanexplain) is not built (see the brief).

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
>>> round(component.estimated_kgco2e, 2)  # 0.2 kg × 8.3 kgCO₂e/kg
1.66

```

Render the view over the fixture BOM to a standalone HTML file:

```sh
uv run python scripts/build_view.py   # writes build/view.html
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
