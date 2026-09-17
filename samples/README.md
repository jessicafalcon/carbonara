# samples

Real, public source files the connector did **not** generate, kept for the
end-to-end exercise in [BACKLOG.md](../BACKLOG.md) item 3. These are **not** QA
fixtures: they carry no ground truth, so nothing here is used by the determinism
or fill-accuracy suites. The point is only to prove the drift gate and the field
normalizers survive a file made elsewhere.

## `us_textile_imports_by_fiber.csv`

U.S. textile imports by fiber and end-use, an annual time series.

- **Source:** USDA Economic Research Service, *U.S. textile imports, by fiber*
  (Table 1), compiled from U.S. Department of Commerce / Census Bureau trade data
  — <https://www.ers.usda.gov/data-products/textiles-and-apparel/>
- **Retrieved:** 2026-09-17, unmodified.
- **Shape:** 1,332 rows; columns `table_num, table_name, Item, fiber, period,
  period_name, value, unit`. Genuinely messy in the way a real export is — a
  quoted field with an embedded comma (`"U.S. textile imports, by fiber"`).

It is aggregate statistics, not a component BOM, so it has none of the canonical
BOM columns. That is the point: the drift gate should refuse it for review rather
than process it, and the normalizers should handle its real values without
crashing. Run the exercise with:

```sh
uv run python scripts/real_file_exercise.py
```

### What it shows

- **Ingest survives the mess.** The quoted-comma field parses correctly and the
  file is profiled without error (encoding `utf-8`, 1,332 rows).
- **The drift gate refuses it.** None of the source columns match the BOM
  contract, so the gate returns `review_required` with no mapping — a real,
  wrong-shaped file is stopped for review, never silently processed.
- **The normalizers hold.** Fed the real `fiber` values, `resolve_material`
  resolves `Cotton → cotton` and flags `Wool`, `Silk`, `Linen`, `Synthetic` as
  unresolved (they are not in the apparel material vocabulary) rather than
  guessing; `parse_date` returns null for the year-only `period` values. Every
  real value produced a clean result or an honest null/flag — no exceptions.

The full fill → footprint path is deliberately not exercised: this file has no
per-component weights, suppliers, or SKUs, and no public per-component apparel BOM
exists to stand in for one. The drift gate is exactly the safety net for that —
it stops here.

