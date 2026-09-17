"""Admit a source file: detect, hash, store bytes, register idempotently, gate on drift."""

from __future__ import annotations

import csv
import dataclasses
import datetime
import enum
import hashlib
import io
import json
import pathlib
import zipfile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from carbonara.profile import ColumnType, Profile, profile_table
from carbonara.source_schema import (
    EXPECTED_SOURCE_SCHEMA,
    MappingProposal,
    SchemaDiff,
    diff_schema,
    propose_mapping,
    schema_of,
)

__all__ = [
    "IngestResult",
    "IngestStatus",
    "SourceFormat",
    "UnsupportedFormatError",
    "admit",
    "content_hash",
    "detect_format",
    "read_rows",
    "read_source",
]

#: ZIP local-file-header magic; an XLSX is a ZIP container.
_ZIP_MAGIC = b"PK\x03\x04"


class SourceFormat(enum.StrEnum):
    """The detected file format."""

    CSV = "csv"
    XLSX = "xlsx"


class IngestStatus(enum.StrEnum):
    """The outcome of admitting a file.

    >>> IngestStatus("review_required")
    <IngestStatus.REVIEW_REQUIRED: 'review_required'>
    """

    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    DUPLICATE = "duplicate"


class UnsupportedFormatError(Exception):
    """Raised for a file whose format is detected but cannot be parsed.

    Both CSV and XLSX are parsed; this fires only when a file carries the XLSX
    (ZIP) signature but is not a readable workbook — surfaced as a clear cause
    rather than a raw openpyxl/zip traceback (input-boundary hardening).
    """


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class IngestResult:
    """What admitting a file produced.

    ``profile``/``schema_diff``/``mapping_proposal`` are populated only when the
    file was processed: a duplicate short-circuits before profiling, and a clean
    accept has no drift to propose.
    """

    content_hash: str
    source_format: SourceFormat
    status: IngestStatus
    stored_path: pathlib.Path
    encoding: str = "utf-8"
    profile: Profile | None = None
    schema_diff: SchemaDiff | None = None
    mapping_proposal: MappingProposal | None = None


def content_hash(raw: bytes) -> str:
    """The sha256 hex digest of the raw bytes — the file's identity."""
    return hashlib.sha256(raw).hexdigest()


def detect_format(raw: bytes) -> SourceFormat:
    """Detect CSV vs XLSX by content, not extension."""
    return SourceFormat.XLSX if raw.startswith(_ZIP_MAGIC) else SourceFormat.CSV


def _decode(raw: bytes) -> tuple[str, str]:
    """Decode source bytes as UTF-8, falling back to CP1252, returning (text, encoding).

    Real vendor exports are often Windows-1252 / Latin-1, not UTF-8. CP1252 maps
    every byte, so a Western file never fails to decode; the encoding used is
    returned so provenance can record which one read the file.
    """
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace"), "cp1252"  # unreachable: cp1252 maps all bytes


def _read_csv(raw: bytes) -> tuple[tuple[str, ...], list[dict[str, str]], str]:
    text, encoding = _decode(raw)
    reader = csv.DictReader(io.StringIO(text))
    columns = tuple(reader.fieldnames or ())
    rows = [{key: (value or "") for key, value in row.items()} for row in reader]
    return columns, rows, encoding


def _cell_str(value: object) -> str:
    """Convert one XLSX cell to the canonical string the CSV path would carry.

    Only three openpyxl cell types need more than ``str(value)``, so only those
    are special-cased: a blank is ``""`` (not ``"None"``), an integer-valued float
    keeps no trailing ``.0``, and an Excel date cell — a ``datetime`` at midnight —
    becomes an ISO date so ``order_date`` parses like the CSV convention. Text,
    ints, and a genuine timestamp already stringify correctly. Deterministic and
    locale-free.

    >>> _cell_str(7), _cell_str(6.26), _cell_str(3400.0), _cell_str(None)
    ('7', '6.26', '3400', '')
    >>> _cell_str(datetime.datetime(2024, 1, 8))
    '2024-01-08'
    """
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, datetime.datetime) and value.hour == value.minute == value.second == value.microsecond == 0:
        return value.date().isoformat()
    return str(value)


def _read_xlsx(raw: bytes) -> tuple[tuple[str, ...], list[dict[str, str]], str]:
    """Read the first sheet of an XLSX into (columns, string rows, encoding).

    openpyxl reads the OOXML directly and every cell is converted to a string
    here (:func:`_cell_str`), so an XLSX follows the same path a CSV does with no
    pandas type inference: fixed first-sheet selection, no locale-dependent number
    or date parsing. XLSX character data is UTF-8 (OOXML), so the encoding is
    recorded as ``utf-8``. A fully blank row is skipped, as it would be in a CSV.
    """
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except (OSError, zipfile.BadZipFile, InvalidFileException) as error:
        raise UnsupportedFormatError(f"XLSX signature but not a readable workbook: {error}") from error
    try:
        sheet = workbook[workbook.sheetnames[0]]  # first sheet by position — deterministic
        row_iter = sheet.iter_rows(values_only=True)
        columns = tuple(_cell_str(value) for value in next(row_iter, ()))
        rows: list[dict[str, str]] = []
        for values in row_iter:
            cells = [_cell_str(value) for value in values]
            if not any(cells):
                continue
            rows.append({column: (cells[i] if i < len(cells) else "") for i, column in enumerate(columns)})
    finally:
        workbook.close()
    return columns, rows, "utf-8"


def read_source(raw: bytes, source_format: SourceFormat) -> tuple[tuple[str, ...], list[dict[str, str]], str]:
    """Parse raw bytes of a supported format into (columns, string rows, encoding)."""
    return _read_xlsx(raw) if source_format is SourceFormat.XLSX else _read_csv(raw)


def read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    """Read a CSV or XLSX source file into pipeline-ready string rows.

    The counterpart to :func:`admit`'s gate: ``admit`` decides whether to accept a
    file; this reads an accepted file's rows for :func:`carbonara.pipeline.run`.
    Format is detected by content, so the caller need not know it — the same call
    reads either format identically.
    """
    raw = path.read_bytes()
    _, rows, _ = read_source(raw, detect_format(raw))
    return rows


def _registry_path(root: pathlib.Path) -> pathlib.Path:
    return root / "registry.json"


def _accepted_schema_path(root: pathlib.Path) -> pathlib.Path:
    return root / "accepted_schema.json"


def _stored_path(root: pathlib.Path, digest: str, fmt: SourceFormat) -> pathlib.Path:
    return root / "raw" / f"{digest}.{fmt.value}"


def _load_registry(root: pathlib.Path) -> dict[str, dict[str, str]]:
    path = _registry_path(root)
    return json.loads(path.read_text()) if path.exists() else {}


def _save_registry(root: pathlib.Path, registry: dict[str, dict[str, str]]) -> None:
    _registry_path(root).write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n")


def _load_baseline(root: pathlib.Path) -> dict[str, ColumnType]:
    """The last accepted schema, else the versioned expected schema."""
    path = _accepted_schema_path(root)
    if not path.exists():
        return EXPECTED_SOURCE_SCHEMA
    # Stored as an ordered [name, type] list so column order survives the round-trip.
    return {name: ColumnType(value) for name, value in json.loads(path.read_text())}


def _save_baseline(root: pathlib.Path, schema: dict[str, ColumnType]) -> None:
    pairs = [[name, dtype.value] for name, dtype in schema.items()]
    _accepted_schema_path(root).write_text(json.dumps(pairs, indent=2) + "\n")


def admit(path: pathlib.Path, store_root: pathlib.Path, *, rerun: bool = False) -> IngestResult:
    """Admit one source file into the store, gating on schema drift.

    A new file is stored, registered, profiled, and gated. Re-admitting identical
    bytes is a no-op unless ``rerun`` is set: idempotency keys on the content
    hash, not the filename. A clean schema is accepted and recorded as the new
    baseline; any drift halts as ``REVIEW_REQUIRED`` with a mapping proposal.
    """
    raw = path.read_bytes()
    fmt = detect_format(raw)
    digest = content_hash(raw)
    stored = _stored_path(store_root, digest, fmt)
    registry = _load_registry(store_root)
    if digest in registry and not rerun:
        return IngestResult(
            content_hash=digest,
            source_format=fmt,
            status=IngestStatus.DUPLICATE,
            stored_path=stored,
            encoding=registry[digest].get("encoding", "utf-8"),
        )

    # Parse before storing, so a file that carries the XLSX signature but cannot be
    # read as a workbook fails without leaving unusable bytes in the store.
    columns, rows, encoding = read_source(raw, fmt)

    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(raw)  # immutable original; overwriting with identical bytes is a no-op

    profile = profile_table(columns, rows)
    diff = diff_schema(profile, _load_baseline(store_root))

    if diff.is_drift:
        status = IngestStatus.REVIEW_REQUIRED
        proposal: MappingProposal | None = propose_mapping(diff)
    else:
        status = IngestStatus.ACCEPTED
        proposal = None
        _save_baseline(store_root, schema_of(profile))

    registry[digest] = {
        "filename": path.name,
        "format": fmt.value,
        "schema_status": status.value,
        "encoding": encoding,
    }
    _save_registry(store_root, registry)

    return IngestResult(
        content_hash=digest,
        source_format=fmt,
        status=status,
        stored_path=stored,
        encoding=encoding,
        profile=profile,
        schema_diff=diff,
        mapping_proposal=proposal,
    )
