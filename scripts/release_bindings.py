"""Shared normalization helpers for release provenance identities."""

from __future__ import annotations

import re
from typing import Any

_ATTESTATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")


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


def required_text(value: Any, label: str) -> str:
    """Require one non-empty textual provenance value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def required_git_object(value: Any, label: str) -> str:
    """Require one lowercase 40-character Git object ID."""
    text = required_text(value, label)
    if _GIT_OBJECT_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a 40-character lowercase Git SHA")
    return text


def required_positive_integer(value: Any, label: str) -> str:
    """Require one positive decimal identifier represented as text."""
    text = required_text(value, label)
    if _POSITIVE_INTEGER_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a positive decimal integer")
    return text


def required_repository(value: Any, label: str) -> str:
    """Require one safe GitHub owner/name repository identity."""
    text = required_text(value, label)
    if _REPOSITORY_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must use owner/name syntax")
    return text
