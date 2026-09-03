"""POWER Canonical JSON v1 Authoritative Serializer and Cryptographic Hashing.

Contract:
- POWER Canonical JSON v1 is the authoritative serialization contract for ProjectEvent v1.
- sort_keys=True
- ensure_ascii=False
- separators=(",", ":")
- allow_nan=False
- UTF-8 encoding without BOM.
- Non-finite numbers (NaN, Infinity, -Infinity) are rejected fail-closed.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _check_floats(obj: Any) -> None:
    """Recursively reject non-finite float values (NaN, +inf, -inf) fail-closed."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("NaN and Infinity values are strictly forbidden in canonical JSON")
    elif isinstance(obj, dict):
        for v in obj.values():
            _check_floats(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_floats(item)


def canonical_json_dumps(data: Any) -> str:
    """Serialize data into a deterministic POWER Canonical JSON v1 string.

    Contract:
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    Encoding: UTF-8 without BOM. Non-finite numbers (NaN, Infinity, -Infinity) are rejected fail-closed.
    """
    _check_floats(data)
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize data to UTF-8 bytes using POWER Canonical JSON v1."""
    return canonical_json_dumps(data).encode("utf-8")


def compute_payload_digest(payload: dict[str, Any]) -> str:
    """Compute SHA-256 hex digest of canonical JSON encoded payload."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def compute_event_hash(event: dict[str, Any]) -> str:
    """Compute full envelope SHA-256 digest over integrity_record.

    Seals the canonical ProjectEvent excluding only the event_hash field itself.
    """
    integrity_record = {k: v for k, v in event.items() if k != "event_hash"}
    return hashlib.sha256(canonical_json_bytes(integrity_record)).hexdigest()


def compute_command_fingerprint(
    *,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    artifact_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    source: str | None = None,
    session_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> str:
    """Compute SHA-256 fingerprint for append command parameters."""
    canonical_dict = {
        "actor": actor,
        "artifact_refs": sorted(artifact_refs or []),
        "causation_id": causation_id or "",
        "correlation_id": correlation_id or "",
        "event_type": event_type,
        "evidence_refs": sorted(evidence_refs or []),
        "payload": payload,
        "session_id": session_id or "",
        "source": source or "",
    }
    return hashlib.sha256(canonical_json_bytes(canonical_dict)).hexdigest()

