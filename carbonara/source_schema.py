"""The expected raw-source schema, plus the drift diff and mapping proposal it feeds."""

from __future__ import annotations

import dataclasses
import difflib

from carbonara.profile import ColumnType, Profile

__all__ = [
    "ALIASES",
    "EXPECTED_SOURCE_SCHEMA",
    "MappingProposal",
    "SCHEMA_VERSION",
    "SchemaDiff",
    "diff_schema",
    "propose_mapping",
    "schema_of",
]

#: Version of the expected-source contract below. Bump on any deliberate change
#: so a schema revision is a new version, never a silent mutation (brief §8.3).
SCHEMA_VERSION = "source_v1"

#: The raw vendor file's known shape: column names in order, each with the coarse
#: type it actually arrives as. Weights and dates are ``string`` because they
#: arrive as free text (``250g``, malformed dates) — normalizing them is Phase 3,
#: so the gate must not mistake that messiness for a type change. Grounded in the
#: fixture's own profile, not guessed.
EXPECTED_SOURCE_SCHEMA: dict[str, ColumnType] = {
    "source_row_id": ColumnType.INTEGER,
    "style_id": ColumnType.STRING,
    "sku": ColumnType.STRING,
    "component": ColumnType.STRING,
    "material": ColumnType.STRING,
    "composition": ColumnType.STRING,
    "net_weight": ColumnType.STRING,
    "supplier": ColumnType.STRING,
    "country": ColumnType.STRING,
    "order_date": ColumnType.STRING,
    "quantity": ColumnType.INTEGER,
    "unit_price": ColumnType.FLOAT,
}

#: Known vendor spellings → the expected column they mean. The deterministic,
#: citable first pass of a mapping proposal, tried before any fuzzy match.
ALIASES: dict[str, str] = {
    "vendor": "supplier",
}

#: Minimum SequenceMatcher ratio for a fuzzy rename proposal. Fixed, so a
#: proposal is reproducible; a near-miss below this is left for the reviewer.
_FUZZY_THRESHOLD = 0.8


def schema_of(profile: Profile) -> dict[str, ColumnType]:
    """The comparable schema (name → coarse type) of a profiled file."""
    return {column.name: column.dtype for column in profile.columns}


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class SchemaDiff:
    """How a profile departs from a baseline schema, by the brief's triggers.

    ``renamed`` is not a field: a rename surfaces as one ``added`` + one
    ``removed`` that :func:`propose_mapping` pairs. Columns are matched by name,
    so a pure reorder is not drift.
    """

    added: tuple[str, ...]
    removed: tuple[str, ...]
    type_changed: tuple[tuple[str, ColumnType, ColumnType], ...]

    @property
    def is_drift(self) -> bool:
        """True if any add/remove/type-change trips the gate."""
        return bool(self.added or self.removed or self.type_changed)


def diff_schema(profile: Profile, baseline: dict[str, ColumnType]) -> SchemaDiff:
    """Diff a profile against a baseline schema.

    A column typed ``empty`` (all-blank in this file) carries no type evidence,
    so it never counts as a type change.

    >>> from carbonara.profile import profile_table
    >>> prof = profile_table(("vendor",), [{"vendor": "Acme"}])
    >>> diff = diff_schema(prof, {"supplier": ColumnType.STRING})
    >>> diff.added, diff.removed
    (('vendor',), ('supplier',))
    >>> diff.is_drift
    True
    """
    observed = schema_of(profile)
    added = tuple(name for name in observed if name not in baseline)
    removed = tuple(name for name in baseline if name not in observed)
    type_changed = tuple(
        (name, baseline[name], observed[name])
        for name in observed
        if name in baseline and observed[name] is not baseline[name] and observed[name] is not ColumnType.EMPTY
    )
    return SchemaDiff(added=added, removed=removed, type_changed=type_changed)


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class MappingProposal:
    """A deterministic rename proposal for a reviewer — never an applied edit.

    ``renames`` maps an added column to the baseline column it likely is;
    ``unresolved_added`` and ``unresolved_removed`` are what no rule could pair.
    """

    renames: dict[str, str]
    unresolved_added: tuple[str, ...]
    unresolved_removed: tuple[str, ...]


def propose_mapping(diff: SchemaDiff) -> MappingProposal:
    """Propose renames for a drift: known aliases first, then bounded fuzzy match.

    >>> diff = SchemaDiff(added=("vendor",), removed=("supplier",), type_changed=())
    >>> propose_mapping(diff).renames
    {'vendor': 'supplier'}
    """
    available = list(diff.removed)
    renames: dict[str, str] = {}
    unresolved_added: list[str] = []
    for source in diff.added:
        target = _match(source, available)
        if target is None:
            unresolved_added.append(source)
        else:
            renames[source] = target
            available.remove(target)
    return MappingProposal(
        renames=renames,
        unresolved_added=tuple(unresolved_added),
        unresolved_removed=tuple(available),
    )


def _match(source: str, candidates: list[str]) -> str | None:
    """The alias target if known and available, else the best fuzzy match, else None."""
    alias = ALIASES.get(source)
    if alias in candidates:
        return alias
    best: tuple[float, str] | None = None
    for candidate in candidates:  # baseline order → deterministic tie-break
        ratio = difflib.SequenceMatcher(None, source, candidate).ratio()
        if ratio >= _FUZZY_THRESHOLD and (best is None or ratio > best[0]):
            best = (ratio, candidate)
    return best[1] if best else None
