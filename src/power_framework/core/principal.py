"""Trusted local principal bindings for the application boundary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

PrincipalBinding = Literal[
    "WEB_SIGNED_SESSION",
    "LOCAL_CLI",
    "LOCAL_MCP_STDIO",
    "SYSTEM_INTERNAL",
]

_PRINCIPAL_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ISSUED = object()


@dataclass(frozen=True)
class Principal:
    """A server-issued, non-secret identity binding for one application call.

    The public constructor deliberately cannot issue a binding. Transport
    adapters must use one of the named factories, which keeps an attribution
    label separate from the proof that the local transport was trusted.
    """

    ref: str
    binding: PrincipalBinding
    valid: bool = True
    expires_at: datetime | None = None
    _issued: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issued is not _ISSUED:
            raise ValueError("principal must be issued by a trusted binding factory")
        if not _PRINCIPAL_REF_PATTERN.fullmatch(self.ref):
            raise ValueError("principal ref must be a safe opaque token")
        if self.binding not in {
            "WEB_SIGNED_SESSION",
            "LOCAL_CLI",
            "LOCAL_MCP_STDIO",
            "SYSTEM_INTERNAL",
        }:
            raise ValueError("unsupported principal binding")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("principal expiry must include a timezone")
            object.__setattr__(self, "expires_at", self.expires_at.astimezone(UTC))

    @classmethod
    def _issue(
        cls,
        ref: str,
        binding: PrincipalBinding,
        *,
        expires_at: datetime | None = None,
        proof: object,
    ) -> Principal:
        if proof is not _ISSUED:
            raise ValueError("principal must be issued by a trusted binding factory")
        return cls(ref=ref, binding=binding, expires_at=expires_at, _issued=proof)

    @classmethod
    def web_signed_session(
        cls,
        subject: str,
        *,
        expires_at: datetime | None = None,
    ) -> Principal:
        """Bind a verified signed-session subject without retaining the subject."""
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 256:
            raise ValueError("session subject must be a bounded non-empty string")
        reference = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:32]
        return cls._issue(
            f"web-{reference}",
            "WEB_SIGNED_SESSION",
            expires_at=expires_at,
            proof=_ISSUED,
        )

    @classmethod
    def local_cli(cls) -> Principal:
        """Issue the trusted principal for one local CLI/library process."""
        return cls._issue("local-cli", "LOCAL_CLI", proof=_ISSUED)

    @classmethod
    def local_mcp_stdio(cls) -> Principal:
        """Issue the trusted principal for the local MCP stdio process."""
        return cls._issue("local-mcp-stdio", "LOCAL_MCP_STDIO", proof=_ISSUED)

    @classmethod
    def system_internal(cls) -> Principal:
        """Issue the non-expiring binding for an explicitly internal operation."""
        return cls._issue("system-internal", "SYSTEM_INTERNAL", proof=_ISSUED)

    def is_valid(self, *, now: datetime | None = None) -> bool:
        """Return whether this binding is currently usable for a mutation."""
        if not self.valid:
            return False
        if self.expires_at is None:
            return True
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC) < self.expires_at


__all__ = ["Principal", "PrincipalBinding"]
