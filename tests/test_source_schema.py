"""Drift detection across all four triggers and the deterministic mapping proposal."""

from __future__ import annotations

from carbonara.profile import ColumnType, profile_table
from carbonara.source_schema import (
    EXPECTED_SOURCE_SCHEMA,
    SchemaDiff,
    diff_schema,
    propose_mapping,
)


def _profile(schema: dict[str, str]):
    return profile_table(tuple(schema), [schema])


_TYPED_CELL = {
    ColumnType.STRING: "abc",
    ColumnType.INTEGER: "1",
    ColumnType.FLOAT: "1.5",
    ColumnType.DATE: "2024-01-15",
}


def test_matching_schema_is_not_drift():
    # One row typed to match the expected schema: no add/remove/type-change.
    row = {name: _TYPED_CELL[t] for name, t in EXPECTED_SOURCE_SCHEMA.items()}
    diff = diff_schema(profile_table(tuple(EXPECTED_SOURCE_SCHEMA), [row]), EXPECTED_SOURCE_SCHEMA)
    assert not diff.is_drift


def test_added_and_removed_columns_are_drift():
    diff = diff_schema(
        _profile({"supplier": "Acme", "extra": "x"}), {"supplier": ColumnType.STRING, "gone": ColumnType.STRING}
    )
    assert diff.added == ("extra",)
    assert diff.removed == ("gone",)
    assert diff.is_drift


def test_type_change_on_shared_column_is_drift():
    diff = diff_schema(_profile({"quantity": "not-a-number"}), {"quantity": ColumnType.INTEGER})
    assert diff.type_changed == (("quantity", ColumnType.INTEGER, ColumnType.STRING),)


def test_all_blank_column_carries_no_type_evidence():
    # An all-blank shared column is EMPTY, not a type change against a typed baseline.
    diff = diff_schema(_profile({"quantity": ""}), {"quantity": ColumnType.INTEGER})
    assert diff.type_changed == ()
    assert not diff.is_drift


def test_known_alias_wins_over_fuzzy():
    diff = SchemaDiff(added=("vendor",), removed=("supplier", "vender"), type_changed=())
    # 'vender' is a closer string, but the alias table pins vendor→supplier.
    assert propose_mapping(diff).renames["vendor"] == "supplier"


def test_fuzzy_match_above_threshold_then_unresolved():
    # A near-spelling ('quantiy') matches; an unrelated column does not.
    diff = SchemaDiff(added=("quantiy", "colour"), removed=("quantity",), type_changed=())
    proposal = propose_mapping(diff)
    assert proposal.renames == {"quantiy": "quantity"}
    assert proposal.unresolved_added == ("colour",)
    assert proposal.unresolved_removed == ()


def test_each_baseline_column_claimed_once():
    diff = SchemaDiff(added=("supplier1", "supplier2"), removed=("supplier",), type_changed=())
    proposal = propose_mapping(diff)
    assert len(proposal.renames) == 1
    assert "supplier2" in proposal.unresolved_added
