"""The augmentation helper preserves a cell's lineage instead of clobbering it."""

from __future__ import annotations

import bloodline as bl
import pandas as pd

from carbonara.augment import RuleRecord, augment_lineage, augment_source, lineage_history
from carbonara.fill import fill_weights
from carbonara.lineage import apply_lineage, to_frame
from carbonara.materialize import materialize
from carbonara.normalize import normalize_records

_NORMALIZE = bl.Source(
    source_type="normalize_material",
    source_metadata={"rule_id": "material_lower", "rule_version": "v1"},
)
_RESOLVE = RuleRecord(rule_id="material_resolve", rule_version="v1", source_type="reference_resolve", confidence=0.9)


def _seed(frame: pd.DataFrame, source: bl.Source, *, column: str) -> pd.DataFrame:
    """Attach an initial single Source to a whole column (the pre-augment state)."""
    return bl.apply_data_lineage(table=frame.copy(), default_source=source, column_names=[column], override=True)


def _materials(*values: str) -> pd.DataFrame:
    return pd.DataFrame({"record_id": [f"r{i}" for i in range(len(values))], "material": list(values)})


def test_first_augmentation_seeds_the_list_and_keeps_the_original():
    frame = _seed(_materials("cotton", "polyester"), _NORMALIZE, column="material")
    out = augment_lineage(frame, record=_RESOLVE, row_mask=pd.Series([True, True]), column="material")

    head = out.iloc[0]["data_lineage"]["material"]
    assert head["source_type"] == "reference_resolve"  # the head is the latest rule
    history = lineage_history(head)
    assert [(h["source_type"], h["rule_id"]) for h in history] == [
        ("normalize_material", "material_lower"),  # the original, folded in as entry 0
        ("reference_resolve", "material_resolve"),
    ]
    assert history[1]["confidence"] == 0.9


def test_second_augmentation_appends_oldest_to_newest():
    frame = _seed(_materials("cotton"), _NORMALIZE, column="material")
    once = augment_lineage(frame, record=_RESOLVE, row_mask=pd.Series([True]), column="material")
    twice = augment_lineage(
        once,
        record=RuleRecord(rule_id="review_approve", rule_version="v1", source_type="reference_resolve"),
        row_mask=pd.Series([True]),
        column="material",
    )
    history = lineage_history(twice.iloc[0]["data_lineage"]["material"])
    assert [h["rule_id"] for h in history] == ["material_lower", "material_resolve", "review_approve"]


def test_augment_preserves_where_plain_override_clobbers():
    frame = _seed(_materials("cotton"), _NORMALIZE, column="material")
    # Bloodline's own override drops the original: one Source, no lifecycle.
    clobbered = _seed(
        frame, bl.Source(source_type="reference_resolve", source_metadata={"rule_id": "x"}), column="material"
    )
    assert lineage_history(clobbered.iloc[0]["data_lineage"]["material"]) == []

    augmented = augment_lineage(frame, record=_RESOLVE, row_mask=pd.Series([True]), column="material")
    assert len(lineage_history(augmented.iloc[0]["data_lineage"]["material"])) == 2


def test_unsourced_cell_seeds_a_single_entry_without_a_fabricated_original():
    head = augment_source(None, RuleRecord(rule_id="grouped_median", rule_version="v1", source_type="grouped_median"))
    assert head.source_type == "grouped_median"
    assert [h["rule_id"] for h in lineage_history(head)] == ["grouped_median"]


def test_only_masked_cells_and_the_named_column_change():
    frame = _materials("cotton", "wool")
    frame["country"] = ["PT", "CN"]
    frame = _seed(frame, _NORMALIZE, column="material")
    frame = _seed(
        frame, bl.Source(source_type="normalize_country", source_metadata={"rule_id": "iso"}), column="country"
    )

    out = augment_lineage(frame, record=_RESOLVE, row_mask=pd.Series([True, False]), column="material")

    assert lineage_history(out.iloc[0]["data_lineage"]["material"])  # row 0 augmented
    assert out.iloc[1]["data_lineage"]["material"] == frame.iloc[1]["data_lineage"]["material"]  # row 1 untouched
    assert out.iloc[0]["data_lineage"]["country"] == frame.iloc[0]["data_lineage"]["country"]  # other column untouched


def test_augmented_lineage_is_byte_identical_across_runs():
    frame = _seed(_materials("cotton", "polyester", "wool"), _NORMALIZE, column="material")
    mask = pd.Series([True, True, True])
    first = augment_lineage(frame, record=_RESOLVE, row_mask=mask, column="material")
    second = augment_lineage(frame, record=_RESOLVE, row_mask=mask, column="material")
    assert first["data_lineage"].astype(str).tolist() == second["data_lineage"].astype(str).tolist()


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


def test_composes_on_top_of_the_real_pipeline_lineage():
    # A grouped-median fill lands the first Source; a second rule augments the same cell.
    rows = [_row(str(i), net_weight=w) for i, w in enumerate(["150 g", "152 g", "148 g", "151 g", "149 g"])]
    rows.append(_row("99", net_weight=""))
    normalized = normalize_records(materialize(rows, {"vendor": "supplier"}))
    filled = fill_weights(normalized.records)
    frame = apply_lineage(to_frame(filled.records), normalized.events + filled.events)

    confirm = RuleRecord(
        rule_id="weight_plausibility", rule_version="v1", source_type="reference_resolve", confidence=0.7
    )
    out = augment_lineage(frame, record=confirm, row_mask=frame["record_id"] == "r0099", column="component_weight_g")

    history = lineage_history(out[out["record_id"] == "r0099"].iloc[0]["data_lineage"]["component_weight_g"])
    assert [h["source_type"] for h in history] == ["grouped_median", "reference_resolve"]
