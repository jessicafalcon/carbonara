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

The full fill → footprint path is not exercised on this file: a fibre-import
table has no per-item weights, suppliers, or SKUs. The drift gate is exactly the
safety net for that — it stops here.

### Why this file, and not a real apparel BOM

A search for a genuinely public apparel file with per-item **material and weight**
turned up two near-misses, both instructive and neither committable here:

- **A brand catalog export** (a Shopify product CSV) is the right *format* — real
  vendor, per-variant grams, price, SKU, multi-row variants — but it is
  *product*-level: material lives in the free-text description, not a column.
  Handed one under a best-effort mapping, the connector stops honestly rather than
  guessing: `materialize` raises `SourceSchemaError: missing required column(s)
  ['source_row_id', 'material']`. (Its repository states no reuse license.)
- **A real garment dataset** — NPCGA, 16 464 Norwegian post-consumer garments
  ([Zenodo 10.5281/zenodo.20440761](https://doi.org/10.5281/zenodo.20440761),
  CC BY-SA 4.0) — *does* carry real fibre composition (`cotton 78% / polyester
  21%`), weight in grams, brand, and country of origin. The block is format, not
  content: it is **semicolon-delimited** (the European convention, where the comma
  is the decimal separator), and the connector's reader is comma-only, so the
  drift gate sees one column and flags it.

So real, openly-licensed apparel data with materials and weights exists; the
remaining gaps are format (a `;`-delimited reader) and granularity
(component-level composition), not availability. The public-domain, comma-delimited
trade table stays the committed sample; the search result is recorded here so the
limitation is neither overstated nor left unexamined.

