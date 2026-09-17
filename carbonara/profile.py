"""Profile a tabular source file: columns, coarse type, null rate, cardinality, samples."""

from __future__ import annotations

import dataclasses
import datetime
import enum
from collections.abc import Mapping, Sequence

__all__ = ["ColumnProfile", "ColumnType", "Profile", "profile_table"]

#: Distinct sample values retained per column — enough to eyeball a column in a
#: review, small enough to stay glanceable.
_SAMPLE_LIMIT = 5


class ColumnType(enum.StrEnum):
    """The coarse type of a raw source column.

    Coarse on purpose: the drift gate compares *structure*, not per-cell
    cleanliness (that is Phase 3). A column is typed by the narrowest kind that
    every non-blank cell satisfies, tried in order integer → float → date →
    string; an all-blank column is ``empty``.

    >>> ColumnType("integer")
    <ColumnType.INTEGER: 'integer'>
    """

    EMPTY = "empty"
    INTEGER = "integer"
    FLOAT = "float"
    DATE = "date"
    STRING = "string"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class ColumnProfile:
    """The observed shape of one column."""

    name: str
    dtype: ColumnType
    null_rate: float
    cardinality: int
    samples: tuple[str, ...]


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class Profile:
    """The observed schema of a tabular file: its columns in header order.

    >>> rows = [{"qty": "3", "note": "a"}, {"qty": "", "note": "b"}]
    >>> prof = profile_table(("qty", "note"), rows)
    >>> prof.names
    ('qty', 'note')
    >>> prof["qty"].dtype, prof["qty"].null_rate
    (<ColumnType.INTEGER: 'integer'>, 0.5)
    >>> prof["note"].cardinality
    2
    """

    columns: tuple[ColumnProfile, ...]

    @property
    def names(self) -> tuple[str, ...]:
        """The column names, in header order."""
        return tuple(column.name for column in self.columns)

    def __getitem__(self, name: str) -> ColumnProfile:
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(name)


def _is_int(value: str) -> bool:
    try:
        int(value)
    except ValueError:
        return False
    return True


def _is_float(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def _infer_type(values: Sequence[str]) -> ColumnType:
    """Type a column by the narrowest kind every non-blank cell satisfies."""
    non_blank = [value for value in values if value.strip() != ""]
    if not non_blank:
        return ColumnType.EMPTY
    if all(_is_int(value) for value in non_blank):
        return ColumnType.INTEGER
    if all(_is_float(value) for value in non_blank):
        return ColumnType.FLOAT
    if all(_is_date(value) for value in non_blank):
        return ColumnType.DATE
    return ColumnType.STRING


def _profile_column(name: str, values: Sequence[str]) -> ColumnProfile:
    non_blank = [value for value in values if value.strip() != ""]
    distinct = sorted(set(non_blank))
    null_rate = round((len(values) - len(non_blank)) / len(values), 6) if values else 0.0
    return ColumnProfile(
        name=name,
        dtype=_infer_type(values),
        null_rate=null_rate,
        cardinality=len(distinct),
        samples=tuple(distinct[:_SAMPLE_LIMIT]),
    )


def profile_table(column_names: Sequence[str], rows: Sequence[Mapping[str, str]]) -> Profile:
    """Profile a table given its header order and its rows.

    Deterministic: same header and rows yield an identical profile — samples are
    the sorted distinct values, so their order does not depend on row order.
    """
    columns = tuple(_profile_column(name, [row.get(name, "") for row in rows]) for name in column_names)
    return Profile(columns=columns)
