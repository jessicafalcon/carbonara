"""Ingest orchestration: detect, hash, store, idempotency, and the drift gate."""

from __future__ import annotations

import csv
import datetime
import io
import pathlib
import zipfile

import openpyxl
import pytest

from carbonara.ingest import (
    IngestStatus,
    SourceFormat,
    UnsupportedFormatError,
    admit,
    content_hash,
    detect_format,
    read_rows,
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


def _clean_xlsx_bytes(rows: int = 1) -> bytes:
    """An XLSX whose header/types match the expected source schema exactly.

    source_row_id and quantity are native integer cells and unit_price a native
    float, to exercise the cell→string conversion; order_date stays free text so
    the column types the same as the CSV path (STRING), not a native date.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(EXPECTED_SOURCE_SCHEMA))
    for i in range(rows):
        sheet.append([i, "STY", "SKU", "shell", "cotton", "100 CO", "200g", "Acme", "PT", "15/01/2024", 1, 9.5])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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


def test_xlsx_is_parsed_through_the_same_gate(tmp_path):
    store = tmp_path / "store"
    result = admit(_write(tmp_path, "book.xlsx", _clean_xlsx_bytes()), store)
    assert result.source_format is SourceFormat.XLSX
    assert result.status is IngestStatus.ACCEPTED  # same schema → accepted, like the CSV
    assert result.encoding == "utf-8"
    assert (store / "accepted_schema.json").exists()
    assert result.stored_path.read_bytes() == _clean_xlsx_bytes()


def test_read_rows_reads_xlsx_cells_faithfully(tmp_path):
    # An integer id keeps no trailing ".0", a float stays a float, a native date
    # cell becomes an ISO string — matching what the CSV path would carry.
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["source_row_id", "unit_price", "order_date"])
    sheet.append([7, 9.5, datetime.datetime(2024, 1, 8)])
    buffer = io.BytesIO()
    workbook.save(buffer)
    [row] = read_rows(_write(tmp_path, "book.xlsx", buffer.getvalue()))
    assert row == {"source_row_id": "7", "unit_price": "9.5", "order_date": "2024-01-08"}


def test_malformed_xlsx_raises_a_clear_error(tmp_path):
    # ZIP signature but no workbook part → a named error, not a raw traceback.
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


def _csv_with_supplier(supplier: str, encoding: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPECTED_SOURCE_SCHEMA)
    writer.writerow(["0", "STY", "SKU", "shell", "cotton", "100 CO", "200g", supplier, "PT", "15/01/2024", "1", "9.5"])
    return buffer.getvalue().encode(encoding)


def test_cp1252_file_is_decoded_and_encoding_recorded(tmp_path):
    raw = _csv_with_supplier("Sté Générale", "cp1252")
    with pytest.raises(UnicodeDecodeError):  # the file is genuinely not UTF-8
        raw.decode("utf-8")
    result = admit(_write(tmp_path, "vendor.csv", raw), tmp_path / "store")
    assert result.encoding == "cp1252"
    assert result.status is IngestStatus.ACCEPTED  # decoded and admitted, not crashed


def test_utf8_file_reads_as_utf8(tmp_path):
    result = admit(_write(tmp_path, "clean.csv", _clean_csv_bytes()), tmp_path / "store")
    assert result.encoding == "utf-8"


def test_bom_v1_duplicate_upload_is_idempotent(tmp_path):
    store = tmp_path / "store"
    admit(_BOM_V1, store)
    registry_before = (store / "registry.json").read_bytes()
    result = admit(_BOM_V1, store)
    assert result.status is IngestStatus.DUPLICATE
    assert (store / "registry.json").read_bytes() == registry_before
    assert len(list((store / "raw").iterdir())) == 1
