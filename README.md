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

Phase 0 — build harness and repo skeleton. The package is a stub; the pipeline
is built phase by phase (see the brief).

```python
>>> import carbonara
>>> carbonara.__version__
'0.1.0'

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
