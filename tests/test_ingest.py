"""Ingest orchestration: detect, hash, store, idempotency, and the drift gate."""

from __future__ import annotations

import csv
import io
import pathlib
import zipfile

import pytest

from carbonara.ingest import (
    IngestStatus,
    SourceFormat,
    UnsupportedFormatError,
    admit,
    content_hash,
    detect_format,
)
from carbonara.source_schema import EXPECTED_SOURCE_SCHEMA


def _clean_csv_bytes(rows: int = 1) -> bytes:
    """A CSV whose header matches the expected source schema exactly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPECTED_SOURCE_SCHEMA)
    for i in range(rows):
        # order_date is free text at ingest (STRING in the expected schema), so a
        # non-ISO value keeps the column typed as it really arrives.
        writer.writerow(
            [str(i), "STY", "SKU", "shell", "cotton", "100 CO", "200g", "Acme", "PT", "15/01/2024", "1", "9.5"]
        )
    return buffer.getvalue().encode("utf-8")


def _write(tmp_path: pathlib.Path, name: str, raw: bytes) -> pathlib.Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def test_detect_format_by_content_not_extension():
    assert detect_format(b"a,b,c\n1,2,3\n") is SourceFormat.CSV
    assert detect_format(b"PK\x03\x04rest-of-a-zip") is SourceFormat.XLSX


def test_clean_file_is_accepted_and_recorded_as_baseline(tmp_path):
    store = tmp_path / "store"
    result = admit(_write(tmp_path, "clean.csv", _clean_csv_bytes()), store)
    assert result.status is IngestStatus.ACCEPTED
    assert result.mapping_proposal is None
    assert (store / "accepted_schema.json").exists()
    assert result.stored_path.read_bytes() == _clean_csv_bytes()


def test_renamed_header_halts_with_mapping_proposal(tmp_path):
    raw = _clean_csv_bytes().replace(b"supplier", b"vendor", 1)
    result = admit(_write(tmp_path, "drift.csv", raw), tmp_path / "store")
    assert result.status is IngestStatus.REVIEW_REQUIRED
    assert result.mapping_proposal is not None
    assert result.mapping_proposal.renames == {"vendor": "supplier"}


def test_duplicate_bytes_are_a_no_op(tmp_path):
    store = tmp_path / "store"
    raw = _clean_csv_bytes()
    admit(_write(tmp_path, "first.csv", raw), store)
    registry_before = (store / "registry.json").read_bytes()

    # Same bytes, different filename: still a duplicate, keyed by content hash.
    result = admit(_write(tmp_path, "second.csv", raw), store)
    assert result.status is IngestStatus.DUPLICATE
    assert result.content_hash == content_hash(raw)
    assert (store / "registry.json").read_bytes() == registry_before


def test_rerun_reprocesses_without_duplicating_bytes(tmp_path):
    store = tmp_path / "store"
    path = _write(tmp_path, "clean.csv", _clean_csv_bytes())
    admit(path, store)
    result = admit(path, store, rerun=True)
    assert result.status is IngestStatus.ACCEPTED
    assert len(list((store / "raw").iterdir())) == 1


def test_xlsx_is_detected_but_not_parsed(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    path = _write(tmp_path, "book.xlsx", buffer.getvalue())
    with pytest.raises(UnsupportedFormatError):
        admit(path, tmp_path / "store")


def test_admit_is_deterministic_across_runs(tmp_path):
    raw = _clean_csv_bytes(rows=3)
    a = admit(_write(tmp_path / "a", "f.csv", raw), tmp_path / "a" / "store")
    b = admit(_write(tmp_path / "b", "f.csv", raw), tmp_path / "b" / "store")
    assert a.content_hash == b.content_hash
    assert a.profile == b.profile
    assert (tmp_path / "a" / "store" / "registry.json").read_bytes() == (
        tmp_path / "b" / "store" / "registry.json"
    ).read_bytes()


# --- §12 fixture-behavior cases, exercised on the shipped fixtures/bom_v1.csv ---

_BOM_V1 = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "bom_v1.csv"


def test_bom_v1_renamed_header_requires_review(tmp_path):
    # The generator ships supplier→vendor, so the first import trips the gate.
    result = admit(_BOM_V1, tmp_path / "store")
    assert result.status is IngestStatus.REVIEW_REQUIRED
    assert result.mapping_proposal is not None
    assert result.mapping_proposal.renames == {"vendor": "supplier"}


def test_bom_v1_duplicate_upload_is_idempotent(tmp_path):
    store = tmp_path / "store"
    admit(_BOM_V1, store)
    registry_before = (store / "registry.json").read_bytes()
    result = admit(_BOM_V1, store)
    assert result.status is IngestStatus.DUPLICATE
    assert (store / "registry.json").read_bytes() == registry_before
    assert len(list((store / "raw").iterdir())) == 1
