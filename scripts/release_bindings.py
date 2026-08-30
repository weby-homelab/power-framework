"""Shared normalization helpers for release provenance identities."""

from __future__ import annotations

import re

_ATTESTATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def normalize_attestation_id(value: str) -> str:
    """Return one canonical GitHub attestation identity.

    Release workflows may receive an ID either as ``123`` or ``github:123``.
    The manifest and receipt use the latter representation, so comparison does
    not depend on which workflow output form was supplied.
    """
    if not isinstance(value, str):
        raise ValueError("attestation identity must be a string")
    candidate = value.strip()
    if candidate.startswith("github:"):
        candidate = candidate.removeprefix("github:")
    if not _ATTESTATION_ID_RE.fullmatch(candidate):
        raise ValueError("attestation identity must contain a safe non-empty identifier")
    return f"github:{candidate}"
