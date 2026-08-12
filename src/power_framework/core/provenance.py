"""Opt-in, content-addressed provenance for external evidence captures."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

PROVENANCE_SCHEMA_VERSION = "power.provenance.v1"
Authority = Literal["unknown", "human", "publisher", "agent"]
Freshness = Literal["unknown", "current", "stale"]
Support = Literal["unverified", "supported", "unsupported"]
Contradiction = Literal["none", "possible", "confirmed"]
ReviewState = Literal["unreviewed", "reviewed", "rejected"]

_AUTHORITIES = {"unknown", "human", "publisher", "agent"}
_FRESHNESS = {"unknown", "current", "stale"}
_SUPPORT = {"unverified", "supported", "unsupported"}
_CONTRADICTIONS = {"none", "possible", "confirmed"}
_REVIEW_STATES = {"unreviewed", "reviewed", "rejected"}


class ProvenanceError(ValueError):
    """Raised when evidence cannot be captured or verified fail-closed."""


@dataclass(frozen=True)
class EvidenceCapture:
    """A content-addressed evidence blob and its provenance record."""

    record: ProvenanceRecord
    blob_path: Path
    record_path: Path


@dataclass(frozen=True)
class ProvenanceRecord:
    """Content-free identity and review state for one captured byte sequence."""

    source_identity: str
    content_sha256: str
    captured_at: datetime
    authority: Authority = "unknown"
    freshness: Freshness = "unknown"
    support: Support = "unverified"
    contradiction: Contradiction = "none"
    review_state: ReviewState = "unreviewed"
    size_bytes: int = 0
    media_type: str = "application/octet-stream"
    egress_policy: str = "deny"

    def __post_init__(self) -> None:
        if not self.source_identity.strip():
            raise ProvenanceError("source_identity must be non-empty")
        if len(self.content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_sha256
        ):
            raise ProvenanceError("content_sha256 must be a lowercase SHA-256 digest")
        if self.captured_at.tzinfo is None:
            raise ProvenanceError("captured_at must include a timezone")
        if self.size_bytes < 0:
            raise ProvenanceError("size_bytes must be non-negative")
        if self.authority not in _AUTHORITIES:
            raise ProvenanceError(f"unsupported authority: {self.authority}")
        if self.freshness not in _FRESHNESS:
            raise ProvenanceError(f"unsupported freshness: {self.freshness}")
        if self.support not in _SUPPORT:
            raise ProvenanceError(f"unsupported support state: {self.support}")
        if self.contradiction not in _CONTRADICTIONS:
            raise ProvenanceError(f"unsupported contradiction state: {self.contradiction}")
        if self.review_state not in _REVIEW_STATES:
            raise ProvenanceError(f"unsupported review state: {self.review_state}")
        if not self.egress_policy.strip():
            raise ProvenanceError("egress_policy must be non-empty")

    def as_dict(self) -> dict[str, object]:
        """Return a stable, content-free JSON-compatible record."""
        return {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "source_identity": self.source_identity,
            "content_sha256": self.content_sha256,
            "captured_at": self.captured_at.astimezone(UTC).isoformat(),
            "authority": self.authority,
            "freshness": self.freshness,
            "support": self.support,
            "contradiction": self.contradiction,
            "review_state": self.review_state,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "egress_policy": self.egress_policy,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ProvenanceRecord:
        """Parse a record and reject unknown schema or malformed state."""
        if payload.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
            raise ProvenanceError("unsupported provenance schema")
        try:
            size_bytes = payload["size_bytes"]
            if not isinstance(size_bytes, int):
                raise ProvenanceError("size_bytes must be an integer")
            captured_at = datetime.fromisoformat(str(payload["captured_at"]))
            return cls(
                source_identity=str(payload["source_identity"]),
                content_sha256=str(payload["content_sha256"]),
                captured_at=captured_at,
                authority=str(payload.get("authority", "unknown")),  # type: ignore[arg-type]
                freshness=str(payload.get("freshness", "unknown")),  # type: ignore[arg-type]
                support=str(payload.get("support", "unverified")),  # type: ignore[arg-type]
                contradiction=str(payload.get("contradiction", "none")),  # type: ignore[arg-type]
                review_state=str(payload.get("review_state", "unreviewed")),  # type: ignore[arg-type]
                size_bytes=size_bytes,
                media_type=str(payload["media_type"]),
                egress_policy=str(payload["egress_policy"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProvenanceError("malformed provenance record") from exc


def capture_bytes(
    content: bytes,
    *,
    source_identity: str,
    media_type: str = "application/octet-stream",
    authority: Authority = "unknown",
    freshness: Freshness = "unknown",
    support: Support = "unverified",
    contradiction: Contradiction = "none",
    review_state: ReviewState = "unreviewed",
    egress_policy: str = "deny",
    captured_at: datetime | None = None,
) -> ProvenanceRecord:
    """Create an opt-in record without persisting or transmitting the bytes."""
    timestamp = captured_at or datetime.now(UTC)
    return ProvenanceRecord(
        source_identity=source_identity,
        content_sha256=hashlib.sha256(content).hexdigest(),
        captured_at=timestamp,
        authority=authority,
        freshness=freshness,
        support=support,
        contradiction=contradiction,
        review_state=review_state,
        size_bytes=len(content),
        media_type=media_type,
        egress_policy=egress_policy,
    )


def capture_file(
    source: Path,
    *,
    source_identity: str,
    media_type: str | None = None,
    max_bytes: int = 16 * 1024 * 1024,
    authority: Authority = "unknown",
    freshness: Freshness = "unknown",
    support: Support = "unverified",
    contradiction: Contradiction = "none",
    review_state: ReviewState = "unreviewed",
    egress_policy: str = "deny",
) -> ProvenanceRecord:
    """Capture only metadata for a bounded regular file, never a symlink."""
    path = Path(source)
    if path.is_symlink() or not path.is_file():
        raise ProvenanceError("provenance source must be a regular non-symlink file")
    if max_bytes < 0:
        raise ProvenanceError("max_bytes must be non-negative")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ProvenanceError("provenance source exceeds max_bytes")
    detected_type = media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return capture_bytes(
        content,
        source_identity=source_identity,
        media_type=detected_type,
        authority=authority,
        freshness=freshness,
        support=support,
        contradiction=contradiction,
        review_state=review_state,
        egress_policy=egress_policy,
    )


def verify_bytes(record: ProvenanceRecord, content: bytes) -> bool:
    """Verify exact captured bytes; false means tampered or unavailable content."""
    return (
        record.size_bytes == len(content)
        and record.content_sha256 == hashlib.sha256(content).hexdigest()
    )


def is_stale(record: ProvenanceRecord, *, max_age: timedelta) -> bool:
    """Return whether the capture is older than a caller-declared freshness window."""
    if max_age < timedelta(0):
        raise ProvenanceError("max_age must be non-negative")
    return datetime.now(UTC) - record.captured_at.astimezone(UTC) > max_age


def same_content(left: ProvenanceRecord, right: ProvenanceRecord) -> bool:
    """Detect duplicate captures without comparing or exposing their source text."""
    return left.content_sha256 == right.content_sha256 and left.size_bytes == right.size_bytes


def _atomic_bytes(path: Path, content: bytes) -> None:
    """Write one evidence blob atomically without newline or encoding changes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise


def capture_file_to_store(
    source: Path,
    store_dir: Path,
    *,
    source_identity: str,
    media_type: str | None = None,
    max_bytes: int = 16 * 1024 * 1024,
    authority: Authority = "unknown",
    freshness: Freshness = "unknown",
    support: Support = "unverified",
    contradiction: Contradiction = "none",
    review_state: ReviewState = "unreviewed",
    egress_policy: str = "deny",
) -> EvidenceCapture:
    """Persist an opt-in exact capture and a sidecar provenance record.

    The blob is de-duplicated by SHA-256. Existing blobs are verified before
    being reused; a mismatch is treated as tampering and fails closed.
    """
    path = Path(source)
    if path.is_symlink() or not path.is_file():
        raise ProvenanceError("provenance source must be a regular non-symlink file")
    if max_bytes < 0:
        raise ProvenanceError("max_bytes must be non-negative")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ProvenanceError("provenance source exceeds max_bytes")
    record = capture_bytes(
        content,
        source_identity=source_identity,
        media_type=media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        authority=authority,
        freshness=freshness,
        support=support,
        contradiction=contradiction,
        review_state=review_state,
        egress_policy=egress_policy,
    )
    root = Path(store_dir).expanduser().resolve()
    blob_path = root / "blobs" / record.content_sha256
    if blob_path.exists():
        if (
            blob_path.is_symlink()
            or not blob_path.is_file()
            or not verify_bytes(record, blob_path.read_bytes())
        ):
            raise ProvenanceError("existing evidence blob failed integrity verification")
    else:
        _atomic_bytes(blob_path, content)

    identity_hash = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()[:16]
    record_path = root / "records" / f"{record.content_sha256}-{identity_hash}.json"
    if record_path.exists():
        try:
            existing = ProvenanceRecord.from_dict(
                json.loads(record_path.read_text(encoding="utf-8"))
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProvenanceError("existing provenance record is malformed") from exc
        if not verify_bytes(existing, blob_path.read_bytes()):
            raise ProvenanceError("existing provenance record failed integrity verification")
        record = existing
    else:
        _atomic_bytes(
            record_path,
            (json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
    return EvidenceCapture(record=record, blob_path=blob_path, record_path=record_path)


def read_captured_evidence(record_path: Path) -> tuple[ProvenanceRecord, bytes]:
    """Read and verify an exact capture, failing closed on missing/tampered data."""
    path = Path(record_path)
    try:
        record = ProvenanceRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        blob_path = path.parent.parent / "blobs" / record.content_sha256
        content = blob_path.read_bytes()
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProvenanceError("captured evidence is unavailable or malformed") from exc
    if not verify_bytes(record, content):
        raise ProvenanceError("captured evidence failed exact-byte verification")
    return record, content
