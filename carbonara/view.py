"""Render the brand-facing view as one self-contained, deterministic HTML page (§10).

``render_view`` is a pure function of the pipeline output — no clock, no
randomness — so it lives in the connector package and re-renders byte-for-byte.
The page shows a run signature, not a wall-clock time. The provenance drawer is
driven by a trace built from the ledger and the raw source rows, embedded as JSON
and toggled with vanilla JS: no server, no network, no framework.
"""

from __future__ import annotations

import html
import json

from carbonara.augment import lineage_history
from carbonara.footprint import (
    Breakdown,
    FactorDiff,
    FootprintResult,
    FootprintStatus,
    by_material,
    summarize,
)
from carbonara.pipeline import PipelineResult
from carbonara.rules import Severity

__all__ = ["render_view"]

# Slate-dashboard palette (data/dev tool, not an editorial page — carbonara-craft).
_CSS = """
:root {
  --bg: #1b2129; --panel: #232c37; --line: #313d4a; --ink: #e7edf3;
  --muted: #8fa3b4; --accent: #20c4a8; --flag: #f87171; --observed: #20c4a8; --filled: #eab308;
  --sans: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
  --mono: ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--mono);
  font-size: 13px; line-height: 1.5; padding: 24px; }
h1, h2 { font-family: var(--sans); font-weight: 600; letter-spacing: -0.01em; }
h1 { font-size: 20px; margin: 0 0 2px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted);
  margin: 0 0 12px; border-bottom: 1px solid var(--line); padding-bottom: 8px; }
a { color: var(--accent); }
.sig { color: var(--muted); font-size: 12px; margin-bottom: 24px; }
.sig b { color: var(--ink); font-weight: 400; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 18px; }
.panel.wide { grid-column: 1 / -1; }
.headline { font-family: var(--sans); font-size: 34px; font-weight: 600; letter-spacing: -0.02em; }
.headline .unit { font-size: 15px; color: var(--muted); font-family: var(--mono); }
.range { color: var(--muted); font-size: 12px; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; color: var(--muted); font-weight: 400; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.06em; padding: 6px 8px; border-bottom: 1px solid var(--line); }
td { padding: 6px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
tr:last-child td { border-bottom: none; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; min-width: 90px; }
.bar > span { display: block; height: 100%; background: var(--accent); }
.split { display: flex; height: 6px; border-radius: 3px; overflow: hidden; min-width: 90px; }
.split .o { background: var(--observed); } .split .f { background: var(--filled); }
.tags { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.tag { font-size: 11px; color: var(--muted); }
.tag b { color: var(--ink); font-weight: 400; }
.tag.applied { color: var(--accent); border: 1px solid var(--accent); border-radius: 10px; padding: 1px 6px; }
.badge { font-size: 10px; padding: 1px 6px; border-radius: 10px; border: 1px solid var(--line); }
.badge.observed { color: var(--observed); border-color: var(--observed); }
.badge.filled { color: var(--filled); border-color: var(--filled); }
.badge.flagged, .sev-high { color: var(--flag); border-color: var(--flag); }
.sev-medium { color: var(--filled); } .sev-low { color: var(--muted); }
.trace { cursor: pointer; color: var(--accent); background: none; border: none; font-family: var(--mono);
  font-size: 12px; padding: 0; }
.delta-up { color: var(--flag); } .delta-down { color: var(--accent); }
.scroll { max-height: 420px; overflow: auto; }
dialog { background: var(--panel); color: var(--ink); border: 1px solid var(--accent); border-radius: 6px;
  max-width: 640px; width: 92%; padding: 0; }
dialog::backdrop { background: rgba(0,0,0,0.6); }
.drawer-head { padding: 16px 18px; border-bottom: 1px solid var(--line); display: flex;
  justify-content: space-between; align-items: baseline; }
.drawer-body { padding: 18px; }
.drawer-body h3 { font-family: var(--sans); font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--muted); margin: 16px 0 8px; }
.drawer-body h3:first-child { margin-top: 0; }
.formula { font-size: 14px; }
.kv { color: var(--muted); } .kv b { color: var(--ink); font-weight: 400; }
.close { cursor: pointer; color: var(--muted); background: none; border: none; font-size: 18px; }
@media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
"""

_JS = """
const TRACE = JSON.parse(document.getElementById('trace-data').textContent);
const dlg = document.getElementById('drawer');
function esc(s){
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}
function openTrace(id){
  const t = TRACE[id]; if(!t) return;
  const rng = t.uncertainty ? ` (range ${t.uncertainty[0].toFixed(2)}–${t.uncertainty[1].toFixed(2)})` : '';
  let ev = t.events.map(e => `<tr><td>${esc(e.rule_id)} <span class="kv">${esc(e.rule_version)}</span></td>`
    + `<td>${esc(e.source_type)}</td><td>${esc(e.column)}</td>`
    + `<td class="num">${esc(e.value_before ?? '—')} → ${esc(e.value_after ?? '—')}</td></tr>`).join('');
  let raw = Object.entries(t.raw).map(([k,v]) => `<tr><td class="kv">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
  const chain = t.material_lineage || [];
  let spine = '';
  if(chain.length > 1){
    const crumbs = chain.map(e =>
      `<span class="tag">${esc(e.source_type)} <span class="kv">${esc(e.rule_id)}</span></span>`).join(' › ');
    spine = `<h3>Cell lineage · material (spine)</h3><div class="tags">${crumbs}</div>`;
  }
  document.getElementById('drawer-title').innerHTML = esc(t.component) + ' · ' + esc(t.record_id);
  document.getElementById('drawer-body').innerHTML =
    `<h3>Estimate</h3><div class="formula">${t.weight_g.toFixed(0)} g / 1000 × `
    + `${t.factor.toFixed(2)} kgCO₂e/kg = <b>${t.estimate.toFixed(3)} kgCO₂e</b>${rng}</div>`
    + `<div class="tags"><span class="tag">material <b>${esc(t.material)}</b></span>`
    + `<span class="tag">weight <b>${esc(t.weight_source)}</b></span>`
    + `<span class="tag">factor <b>${esc(t.factor_source)} ${esc(t.factor_source_version)}</b></span></div>`
    + spine
    + `<h3>Rules applied (ledger)</h3><table><thead><tr><th>rule</th><th>type</th><th>column</th>`
    + `<th class="num">before → after</th></tr></thead><tbody>${ev}</tbody></table>`
    + `<h3>Source row · row ${esc(t.source_row_id)}</h3><table><tbody>${raw}</tbody></table>`;
  dlg.showModal();
}
function closeTrace(){ dlg.close(); }
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _n(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def _bar(fraction: float) -> str:
    return f'<div class="bar"><span style="width:{max(0.0, min(1.0, fraction)) * 100:.1f}%"></span></div>'


def _split(observed: float, filled: float) -> str:
    o, f = observed * 100, filled * 100
    return (
        f'<div class="split"><span class="o" style="width:{o:.1f}%"></span>'
        f'<span class="f" style="width:{f:.1f}%"></span></div>'
    )


def _material_rows(breakdowns: list[Breakdown], total: float) -> str:
    cells = []
    for b in breakdowns:
        share = b.total_kgco2e / total if total else 0.0
        cells.append(
            f"<tr><td>{_esc(b.key)}</td>"
            f'<td class="num">{_n(b.total_kgco2e)}</td>'
            f'<td style="width:120px">{_bar(share)}</td>'
            f'<td class="num">{share * 100:.1f}%</td>'
            f'<td style="width:110px">{_split(b.observed_share, b.filled_share)}</td>'
            f'<td class="num">{b.costed_n}</td></tr>'
        )
    return "".join(cells)


def _diff_rows(diff: FactorDiff) -> str:
    cells = []
    for r in diff.rows:
        cls = "delta-up" if r.delta_kgco2e > 0 else "delta-down"
        cells.append(
            f"<tr><td>{_esc(r.material)}</td>"
            f'<td class="num">{_n(r.factor_from, 2)} → {_n(r.factor_to, 2)}</td>'
            f'<td class="num">{_n(r.total_from)} → {_n(r.total_to)}</td>'
            f'<td class="num {cls}">{"+" if r.delta_kgco2e >= 0 else ""}{_n(r.delta_kgco2e)}</td></tr>'
        )
    return "".join(cells)


def _component_rows(result: FootprintResult) -> str:
    priced = [c for c in result.components if c.estimated_kgco2e is not None]
    priced.sort(key=lambda c: (-(c.estimated_kgco2e or 0.0), c.record_id))
    cells = []
    for c in priced:
        badge = "flagged" if c.status is FootprintStatus.FLAGGED else c.weight_source
        cells.append(
            f"<tr><td>{_esc(c.style_id)}</td><td>{_esc(c.component)}</td><td>{_esc(c.material)}</td>"
            f'<td class="num">{_n(c.weight_g or 0.0, 0)} g <span class="badge {badge}">{badge}</span></td>'
            f'<td class="num">{_n(c.estimated_kgco2e or 0.0, 3)}</td>'
            f'<td class="num">{_esc(c.factor_source_version)}</td>'
            f'<td><button class="trace" onclick="openTrace(\'{_esc(c.record_id)}\')">trace ▸</button></td></tr>'
        )
    return "".join(cells)


def _review_rows(result: PipelineResult) -> str:
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings = sorted(result.findings, key=lambda f: (order[f.severity], f.record_id))
    cells = []
    for f in findings:
        applied = (f.record_id, f.column) in result.resolved_cells
        status = '<span class="tag applied">applied</span>' if applied else '<span class="kv">pending</span>'
        cells.append(
            f"<tr><td>{_esc(f.record_id)}</td><td>{_esc(f.column)}</td><td>{_esc(f.category)}</td>"
            f'<td class="sev-{f.severity.value}">{_esc(f.severity)}</td>'
            f"<td>{_esc(f.message)}</td><td>{_esc(f.proposed_value)}</td><td>{status}</td></tr>"
        )
    return "".join(cells)


def _material_lineage(result: PipelineResult, record_id: str) -> list[dict[str, object]]:
    """The material cell's chained lineage tiers from the Bloodline spine (oldest first)."""
    rows = result.frame.loc[result.frame["record_id"] == record_id, "data_lineage"]
    cell = rows.iloc[0].get("material_normalized") if len(rows) else None
    return [{"source_type": e["source_type"], "rule_id": e["rule_id"]} for e in lineage_history(cell)]


def _trace_data(result: PipelineResult) -> str:
    raw_by_id = {s.record.record_id: (s.record.source_row_id, s.raw) for s in result.records}
    trace: dict[str, object] = {}
    for c in result.footprint.components:
        if c.estimated_kgco2e is None:
            continue
        source_row_id, raw = raw_by_id.get(c.record_id, ("", {}))
        events = [
            {
                "rule_id": row.rule_id,
                "rule_version": row.rule_version,
                "source_type": row.source_type.value,
                "column": row.column,
                "value_before": row.value_before,
                "value_after": row.value_after,
            }
            for row in result.ledger.for_record(c.record_id)
        ]
        trace[c.record_id] = {
            "record_id": c.record_id,
            "source_row_id": source_row_id,
            "component": c.component,
            "material": c.material,
            "weight_g": c.weight_g,
            "weight_source": c.weight_source,
            "estimate": c.estimated_kgco2e,
            "factor": c.factor_kgco2e_per_kg,
            "factor_source": c.factor_source,
            "factor_source_version": c.factor_source_version,
            "uncertainty": list(c.uncertainty_kgco2e) if c.uncertainty_kgco2e else None,
            "events": events,
            "material_lineage": _material_lineage(result, c.record_id),
            "raw": raw,
        }
    # Escape the solidus in any "</..." so a raw value can't close the <script> early.
    return json.dumps(trace, sort_keys=True, ensure_ascii=False).replace("</", "<\\/")


def render_view(result: PipelineResult, *, diff: FactorDiff | None = None, title: str = "carbonara") -> str:
    """Render the full brand-facing view for one pipeline run as an HTML string.

    ``diff`` adds the factor-revision panel when supplied. The output is a
    deterministic function of ``result`` (and ``diff``): same inputs, same bytes.
    """
    summary = summarize(result.footprint)
    materials = by_material(result.footprint)
    lo, hi = summary.uncertainty_kgco2e

    weighted = summary.costed_n + summary.flagged_n
    mapped = sum(1 for c in result.footprint.components if c.material is not None)
    with_country = sum(1 for s in result.records if s.record.factory_country_iso is not None)
    total_rows = len(result.footprint.components)
    high = sum(1 for f in result.findings if f.severity is Severity.HIGH)
    medium = sum(1 for f in result.findings if f.severity is Severity.MEDIUM)
    low = sum(1 for f in result.findings if f.severity is Severity.LOW)

    diff_panel = ""
    if diff is not None:
        pct = (diff.delta_kgco2e / diff.total_from * 100) if diff.total_from else 0.0
        delta_cls = "delta-up" if diff.delta_kgco2e >= 0 else "delta-down"
        sign = "+" if diff.delta_kgco2e >= 0 else ""
        delta_span = f'<span class="{delta_cls}">{sign}{_n(diff.delta_kgco2e)}, {pct:+.1f}%</span>'
        diff_panel = f"""
    <section class="panel wide">
      <h2>Factor revision · {_esc(diff.from_version)} → {_esc(diff.to_version)}</h2>
      <p class="range">Catalog {_n(diff.total_from)} → {_n(diff.total_to)} kgCO₂e ({delta_span}).
        Weights held fixed; a revision is a new run, appended — v1 history is untouched.</p>
      <table><thead><tr><th>material</th><th class="num">factor kgCO₂e/kg</th>
        <th class="num">total kgCO₂e</th><th class="num">delta</th></tr></thead>
        <tbody>{_diff_rows(diff)}</tbody></table>
    </section>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} · footprint</title>
<style>{_CSS}</style>
</head><body>
<h1>{_esc(title)} — catalog footprint</h1>
<p class="sig">run <b>{_esc(result.run_id)}</b> · ruleset <b>{_esc(result.ruleset_version)}</b>
  · factor table <b>{_esc(result.factor_version)}</b> · reference data <b>{_esc(result.reference_digest)}</b>
  · deterministic re-render</p>

<div class="grid">
  <section class="panel">
    <h2>Readiness</h2>
    <div class="headline">{_n(summary.total_kgco2e)} <span class="unit">kgCO₂e</span></div>
    <div class="range">material-stage estimate · fibre/material production only —
      excludes yarn/fabric formation, dyeing, cut-make-trim, transport, and use (§15)</div>
    <div class="range">uncertainty {_n(lo)} – {_n(hi)} kgCO₂e · observed vs filled input share</div>
    <div style="margin:10px 0 4px">{_split(summary.observed_share, summary.filled_share)}</div>
    <div class="tags">
      <span class="tag"><b style="color:var(--observed)">{summary.observed_share * 100:.0f}%</b> observed</span>
      <span class="tag"><b style="color:var(--filled)">{summary.filled_share * 100:.0f}%</b> filled</span>
    </div>
    <div class="tags" style="margin-top:14px">
      <span class="tag">costed <b>{summary.costed_n}</b></span>
      <span class="tag">flagged <b class="delta-up">{summary.flagged_n}</b></span>
      <span class="tag">unmapped <b>{summary.unmapped_n}</b></span>
      <span class="tag">no weight <b>{summary.no_weight_n}</b></span>
    </div>
    <div class="tags" style="margin-top:14px">
      <span class="tag">weight coverage <b>{weighted}/{total_rows}</b></span>
      <span class="tag">material mapped <b>{mapped}/{total_rows}</b></span>
      <span class="tag">country resolved <b>{with_country}/{total_rows}</b></span>
    </div>
    <div class="tags" style="margin-top:14px">
      <span class="tag">findings <b>{len(result.findings)}</b></span>
      <span class="tag">high <b class="delta-up">{high}</b></span>
      <span class="tag">medium <b>{medium}</b></span>
      <span class="tag">low <b>{low}</b></span>
    </div>
  </section>

  <section class="panel">
    <h2>Review queue · {len(result.findings)} findings</h2>
    <div class="scroll"><table><thead><tr><th>record</th><th>column</th><th>category</th>
      <th>sev</th><th>finding</th><th>proposed</th><th>status</th></tr></thead>
      <tbody>{_review_rows(result)}</tbody></table></div>
  </section>

  <section class="panel wide">
    <h2>Footprint · material basket</h2>
    <table><thead><tr><th>material</th><th class="num">kgCO₂e</th><th>share</th>
      <th class="num"></th><th>obs / fill</th><th class="num">n</th></tr></thead>
      <tbody>{_material_rows(materials, summary.total_kgco2e)}</tbody></table>
  </section>
{diff_panel}
  <section class="panel wide">
    <h2>Components · trace any number to its source</h2>
    <div class="scroll"><table><thead><tr><th>style</th><th>component</th><th>material</th>
      <th class="num">weight</th><th class="num">kgCO₂e</th><th class="num">factor</th><th></th></tr></thead>
      <tbody>{_component_rows(result.footprint)}</tbody></table></div>
  </section>
</div>

<dialog id="drawer">
  <div class="drawer-head"><b id="drawer-title" style="font-family:var(--sans)"></b>
    <button class="close" onclick="closeTrace()">✕</button></div>
  <div class="drawer-body" id="drawer-body"></div>
</dialog>

<script id="trace-data" type="application/json">{_trace_data(result)}</script>
<script>{_JS}</script>
</body></html>
"""
