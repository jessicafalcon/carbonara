"""Bloodline lineage tags each filled cell with its tier, deterministically."""

from __future__ import annotations

from carbonara.fill import fill_weights
from carbonara.lineage import apply_lineage, to_frame
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records


def _row(row_id: str, **over: str) -> dict[str, str]:
    row = {
        "source_row_id": row_id,
        "style_id": "TSH-1",
        "sku": f"SKU-{row_id}",
        "component": "shell fabric",
        "material": "cotton",
        "vendor": "Acme Textiles",
        "composition": "100% cotton",
        "net_weight": "150 g",
        "country": "Portugal",
        "order_date": "2024-01-08",
        "quantity": "10",
        "unit_price": "5.0",
    }
    row.update(over)
    return row


def _pipeline(rows: list[dict[str, str]]):
    normalized = normalize_records(materialize(rows, {"vendor": "supplier"}))
    filled = fill_weights(normalized.records)
    frame = to_frame(filled.records)
    return apply_lineage(frame, normalized.events + filled.events), filled


def test_filled_cell_carries_its_tier_in_the_lineage():
    rows = [_row(str(i), net_weight=w) for i, w in enumerate(["150 g", "152 g", "148 g", "151 g", "149 g"])]
    rows.append(_row("99", net_weight=""))
    frame, _ = _pipeline(rows)
    filled_row = frame[frame["record_id"] == "r0099"].iloc[0]
    assert filled_row["data_lineage"]["component_weight_g"]["source_type"] == "grouped_median"


def test_untouched_null_has_no_lineage_source():
    # No value, so Bloodline leaves the cell unsourced; the verdict is on the record.
    frame, filled = _pipeline([_row("1", component="mystery trim", net_weight="")])
    lineage = frame[frame["record_id"] == "r0001"].iloc[0]["data_lineage"]
    assert "component_weight_g" not in lineage
    assert filled.records[0].record.quality_status.value == "action_required"


def test_lineage_is_deterministic():
    rows = [_row(str(i), net_weight=w) for i, w in enumerate(["150 g", "152 g", "148 g", "151 g", "149 g"])]
    rows.append(_row("99", net_weight=""))
    first, _ = _pipeline(rows)
    second, _ = _pipeline(rows)
    assert first["data_lineage"].astype(str).tolist() == second["data_lineage"].astype(str).tolist()
