---
name: carbonara-craft
description: >
  How code is written in the carbonara BOM connector — the craft standard that
  makes every file read as one hand. Python idioms, module/package structure,
  typing, dataclasses, the reuse-first ladder, tooling (uv/ruff/ty/pytest), and
  the doctest-as-documentation testing style. Read this BEFORE writing or
  refactoring any Python in this repo, choosing a dependency, or adding a test.
  Pairs with carbonara-correctness (what makes a change safe), carbonara-voice
  (commits/PRs/comments), and carbonara-efficiency (tokens/caching).
---

# carbonara-craft

The connector is small on purpose. Every file should look like it came from the
same hand: quiet, typed, deterministic, and covered by a check that doubles as
documentation. This skill is *how* we write; `carbonara-correctness` is *what*
keeps it safe.

## Reuse before writing (the lazy-senior ladder)

The best code is the code never written. Before adding anything, stop at the
first rung that holds — but only *after* you've read the task and traced the
real flow end to end:

1. **Does it need to exist?** Speculative need → skip it, say so in one line.
2. **Already in this repo?** Reuse the helper, rule, or contract that's here.
3. **Standard library?** Use it (`pathlib`, `dataclasses`, `enum`, `hashlib`, `csv`, `statistics`).
4. **An installed dependency?** Pandas, DuckDB, and Bloodline are already ours. Use Bloodline for lineage as intended — never reimplement row-level lineage.
5. **One line?** Make it one line.
6. **Only then** write the minimum that works.

No abstraction with a single implementation. No factory for one product. No
config for a value that never changes. Deletion over addition; boring over
clever. A deliberate corner-cut with a known ceiling gets a `# ponytail:`
comment naming the ceiling and the upgrade trigger — e.g.
`# ponytail: O(n²) supplier match, fine at ~500 rows; index if the fixture grows`.

## Module and package shape

- Small, single-concern modules. One clear responsibility per file (`source.py`, `ingest.py`, `ledger.py`, `fill_ladder.py`), not a grab-bag `utils` god-module.
- Every module opens with a one-line docstring stating its job:
  ```python
  """Append-only rule-event ledger (the ordered history of every rule application)."""
  ```
- `from __future__ import annotations` is the first import in every module.
- Declare the public surface with `__all__`. Keep it minimal; everything else is internal.
- Package layout: `carbonara/` (the connector), `tests/`, `references/` (versioned reference/factor CSVs, one citation per row), `fixtures/`.

## Typing

Types are not optional; `ty` runs on every edit.

```python
def normalize_weight(value: float, unit: str) -> float | None: ...
```

- Modern syntax only: `X | None`, `list[str]`, `dict[str, Any]` — never `Optional`, `List`, `Dict` from `typing`.
- Type every public function's parameters and return. `Any` is a smell; reach for a concrete type or a small dataclass first.

## Dataclasses over dicts for contracts

The canonical record, a rule, a source, a ledger event — anything with a fixed
shape — is a dataclass, frozen and keyword-only:

```python
@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Source:
    """Provenance of a single data point."""

    source_type: str
    source_metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
```

`slots=True` for memory, `frozen=True` because records are immutable once
written (governance), `kw_only=True` so call sites read as `Source(source_type=..., ...)`.
A fixed vocabulary (source types, ladder tiers, quality statuses) is an `enum.Enum`.

## Pandas style

- **Never mutate an input frame in place.** Return a new frame (`df.assign(...)`, `df.copy()`), so a rule is a pure `frame -> frame` transform. This is what makes re-runs reproducible and lineage attachable.
- Prefer vectorized/`assign`/`merge` over row loops. When a row loop is genuinely clearer for a rule, keep it small and deterministic.
- Select the columns you need; don't carry the whole frame through a helper that touches two columns.
- Preserve the raw alongside the normalized (`component_weight_g` *and* the original value+unit) — never overwrite the source of truth.

## Naming

Intention-revealing, searchable, no cryptic abbreviations. Functions are
verbs (`parse_composition`, `resolve_country`, `fill_weight`); dataclasses and
enums are nouns (`RuleEvent`, `SourceType`). No single-letter names outside a
tight comprehension. Thresholds are named config, never magic numbers in the body.

## Testing: the check that doubles as documentation

Non-trivial logic leaves exactly **one runnable check** behind. No frameworks
beyond pytest, no fixture pyramids unless the logic demands them.

- **Prefer a doctest** — it proves the behavior *and* shows a reader how to use the thing. Fixtures seed with a fixed `random.seed(42)` so the output is stable. Test-function bodies are often a pure `>>>` narrative:
  ```python
  def test_parse_composition():
      """
      >>> from carbonara.normalize import parse_composition
      >>> parse_composition("70/30 CO/PL")
      {'cotton': 0.7, 'polyester': 0.3}
      """
  ```
- **README doctests are real tests.** `pytest` runs them via `--doctest-glob=*.md`; a `tests/test_readme.py` wires it up with `doctest.ELLIPSIS | NORMALIZE_WHITESPACE`. Keep every `>>>` block in the README executable and correct.
- Reach for a plain `test_*.py` only when a doctest would be contorted (large frames, error paths, parametrized cases). Test names describe behavior: `test_high_spread_group_falls_through_to_reference_constant`.
- Every planted fixture case ([§6](../../../PROJECT-BRIEF.md), [§12](../../../PROJECT-BRIEF.md)) has a test asserting its specified outcome.

## Tooling (the deterministic backbone)

- **uv** for packaging and the lockfile (`uv sync`, `uv run pytest`, `uv lock`).
- **ruff** for format + lint: line-length 120, rules `E, W, F, I, B, UP`. Runs `--fix` on every edit via the hook.
- **ty** for type checking, treated as errors.
- **pre-commit** installed on pre-push (`pre-commit install --hook-type pre-push`): uv-lock, ruff-check, ruff-format, ty.
- Python ≥ 3.11.

Let the hooks and pre-commit do the mechanical enforcement; spend your attention
on the logic and the check.

## Frontend (Phase 5 only)

The brand-facing view is a **data/dev tool**, not an editorial page. State a
concrete, restrained visual direction (a specific palette + type + layout) up
front. Do **not** accept a default cream/serif, warm-editorial look — it reads
wrong for a data-quality console. If direction is open, propose 3–4 distinct
options (bg / accent / typeface + one-line rationale) and build only the chosen
one. Avoid generic AI-slop defaults (Inter/Roboto, purple-on-white gradients,
cookie-cutter card grids); favor clarity, dense information design, and legible
provenance affordances.
