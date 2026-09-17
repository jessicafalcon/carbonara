"""Admit a source file: detect, hash, store bytes, register idempotently, gate on drift."""

from __future__ import annotations

import csv
import dataclasses
import enum
import hashlib
import io
import json
import pathlib

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
    """Raised for a format detected but not parsed in this phase (XLSX)."""


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
    if fmt is SourceFormat.XLSX:
        raise UnsupportedFormatError("XLSX detected; only CSV is parsed in this phase")

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

    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(raw)  # immutable original; overwriting with identical bytes is a no-op

    columns, rows, encoding = _read_csv(raw)
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
