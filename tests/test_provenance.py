"""Opt-in provenance is content-addressed, bounded, and fail-closed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from power_framework.core.provenance import (
    PROVENANCE_SCHEMA_VERSION,
    ProvenanceError,
    capture_bytes,
    capture_file,
    capture_file_to_store,
    is_stale,
    read_captured_evidence,
    same_content,
    verify_bytes,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_provenance_round_trip_and_tamper_detection() -> None:
    captured_at = datetime(2026, 8, 1, tzinfo=UTC)
    record = capture_bytes(
        b"external evidence",
        source_identity="fixture://evidence/1",
        authority="publisher",
        freshness="current",
        support="supported",
        captured_at=captured_at,
    )

    assert record.as_dict()["schema_version"] == PROVENANCE_SCHEMA_VERSION
    assert verify_bytes(record, b"external evidence") is True
    assert verify_bytes(record, b"tampered evidence") is False
    assert same_content(record, type(record).from_dict(record.as_dict()))
    assert is_stale(record, max_age=timedelta(days=1)) is True


def test_provenance_file_capture_is_bounded_and_rejects_unavailable_sources(
    tmp_path: Path,
) -> None:
    source = tmp_path / "evidence.txt"
    source.write_text("captured", encoding="utf-8")
    record = capture_file(source, source_identity="file://evidence.txt", max_bytes=64)
    assert record.size_bytes == len(b"captured")
    assert record.media_type == "text/plain"

    with pytest.raises(ProvenanceError, match="exceeds max_bytes"):
        capture_file(source, source_identity="file://evidence.txt", max_bytes=1)

    link = tmp_path / "link.txt"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ProvenanceError, match="regular non-symlink"):
        capture_file(link, source_identity="file://link.txt")


def test_provenance_rejects_naive_time_and_negative_age() -> None:
    with pytest.raises(ProvenanceError, match="timezone"):
        capture_bytes(
            b"evidence",
            source_identity="fixture://naive",
            captured_at=datetime(2026, 8, 1),
        )

    record = capture_bytes(b"evidence", source_identity="fixture://age")
    with pytest.raises(ProvenanceError, match="max_age"):
        is_stale(record, max_age=timedelta(seconds=-1))


def test_opt_in_capture_is_exact_deduplicated_and_tamper_evident(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"exact external evidence")
    store = tmp_path / "evidence-store"

    first = capture_file_to_store(source, store, source_identity="fixture://source.txt")
    duplicate = capture_file_to_store(source, store, source_identity="fixture://source.txt")
    record, content = read_captured_evidence(first.record_path)

    assert first.blob_path == duplicate.blob_path
    assert first.record_path == duplicate.record_path
    assert record.content_sha256 == first.record.content_sha256
    assert content == b"exact external evidence"

    first.blob_path.write_bytes(b"tampered")
    with pytest.raises(ProvenanceError, match="exact-byte"):
        read_captured_evidence(first.record_path)


def test_opt_in_capture_fails_closed_when_blob_is_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"unavailable source fixture")
    capture = capture_file_to_store(source, tmp_path / "store", source_identity="fixture://source")
    capture.blob_path.unlink()

    with pytest.raises(ProvenanceError, match="unavailable"):
        read_captured_evidence(capture.record_path)
