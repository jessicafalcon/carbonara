"""Coarse-type inference, determinism, and the null/cardinality/sample fields."""

from __future__ import annotations

import pytest

from carbonara.profile import ColumnType, profile_table


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["", "", ""], ColumnType.EMPTY),
        (["1", "2", ""], ColumnType.INTEGER),
        (["1.5", "2", ""], ColumnType.FLOAT),
        (["2024-01-15", "2024-02-01"], ColumnType.DATE),
        (["70/30 CO/PL", "cotton"], ColumnType.STRING),
        (["12/13/2024", "2024-01-15"], ColumnType.STRING),  # malformed date → string
    ],
)
def test_coarse_type_is_narrowest_kind_all_cells_satisfy(values, expected):
    rows = [{"c": value} for value in values]
    assert profile_table(("c",), rows)["c"].dtype is expected


def test_null_rate_and_cardinality_count_blank_and_distinct():
    rows = [{"c": "a"}, {"c": "a"}, {"c": ""}, {"c": "b"}]
    column = profile_table(("c",), rows)["c"]
    assert column.null_rate == 0.25
    assert column.cardinality == 2


def test_samples_are_sorted_distinct_and_row_order_independent():
    forward = [{"c": v} for v in ["b", "a", "c", "a"]]
    reversed_rows = list(reversed(forward))
    assert profile_table(("c",), forward)["c"].samples == ("a", "b", "c")
    assert profile_table(("c",), forward) == profile_table(("c",), reversed_rows)


def test_missing_column_key_treated_as_blank():
    # A row lacking the column reads as a blank cell, not a crash.
    column = profile_table(("c",), [{"other": "x"}])["c"]
    assert column.dtype is ColumnType.EMPTY
    assert column.null_rate == 1.0
