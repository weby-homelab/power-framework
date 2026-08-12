"""Stable application boundary shared by local transports.

The application service owns orchestration for the small 3.5.0 core.  CLI and
MCP adapters may format its envelopes, but they do not need to know about
SQLite, cache generations, or proposal files.  Receipts intentionally contain
hashes and identifiers only; note content is never copied into the audit hook.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from .capabilities import manifest
from .handoff import (
    advance_work_packet,
    create_work_packet,
    list_work_packets,
    read_work_packet,
)
from .memory_api import apply_change, propose_change, read_history
from .searcher import (
    DEFAULT_SEARCH_MODE,
    format_untrusted_search_envelope,
    search_vault,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


ApplicationAuthority = Literal["read-only", "propose", "apply"]


@dataclass(frozen=True)
class RequestContext:
    """Authorization and bounded execution metadata for one use case."""

    actor: str = "local"
    authority: ApplicationAuthority = "read-only"
    idempotency_key: str | None = None
    deadline_ms: int | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise ValueError("actor must be a non-empty string")
        if self.idempotency_key is not None and not _TOKEN_PATTERN.fullmatch(self.idempotency_key):
            raise ValueError("idempotency_key must be a safe token")
        if self.deadline_ms is not None and self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")


@dataclass(frozen=True)
class AuditReceipt:
    """Content-free operation receipt delivered to an optional audit hook."""

    schema_version: str
    operation: str
    status: str
    request_id: str
    idempotency_key: str | None
    data_sha256: str
    duration_ms: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "status": self.status,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "data_sha256": self.data_sha256,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class ApplicationEnvelope:
    """Versioned JSON-compatible result returned by every application use case."""

    operation: str
    status: Literal["ok", "unavailable"]
    data: dict[str, object]
    receipt: AuditReceipt
    schema_version: str = "power.application.v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "status": self.status,
            "data": self.data,
            "receipt": self.receipt.as_dict(),
        }


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ApplicationService:
    """Use-case service for the lean, offline-capable POWER core."""

    def __init__(
        self,
        vault_dir: Path,
        *,
        audit_hook: Callable[[AuditReceipt], None] | None = None,
        search_fn: Callable[..., list[Any]] | None = None,
    ) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self._audit_hook = audit_hook
        self._search_fn = search_fn or search_vault

    def discover(self, *, context: RequestContext | None = None) -> ApplicationEnvelope:
        """Return bounded capability metadata without probing optional runtimes."""
        return self._run(
            "discover",
            context,
            lambda: {"capabilities": manifest(), "probe_provider": False},
        )

    def retrieve(
        self,
        query: str,
        *,
        max_results: int = 20,
        mode: str = DEFAULT_SEARCH_MODE,
        temporal_view: str = "current",
        as_of: str | None = None,
        domain: str | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Retrieve untrusted, provenance-bearing source material."""
        if not query.strip():
            raise ValueError("Search query cannot be empty")
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")

        def execute() -> dict[str, object]:
            results = self._search_fn(
                self.vault_dir,
                query,
                max_results=max_results,
                mode=mode,
                temporal_view=temporal_view,
                as_of=as_of,
                domain=domain,
            )
            return cast(
                "dict[str, object]",
                json.loads(
                    format_untrusted_search_envelope(
                        results,
                        query,
                        mode=mode,
                        vault_dir=self.vault_dir,
                        temporal_view=temporal_view,
                        as_of=as_of,
                    )
                ),
            )

        return self._run("retrieve", context, execute)

    def propose(
        self,
        rel_path: str,
        content: str,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Persist a reviewable proposal, never the target note."""
        request = context or RequestContext(authority="propose")
        if request.authority not in {"propose", "apply"}:
            raise PermissionError("proposal requires propose authority")
        return self._run(
            "propose",
            request,
            lambda: propose_change(
                self.vault_dir,
                rel_path,
                content,
                idempotency_key=request.idempotency_key,
            ),
        )

    def apply(
        self,
        proposal: dict[str, str],
        *,
        approved: bool,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Apply a proposal only with explicit approval authority."""
        request = context or RequestContext(authority="apply")
        if not approved or request.authority != "apply":
            raise PermissionError("apply requires explicit approved=True and apply authority")
        return self._run(
            "apply",
            request,
            lambda: apply_change(
                self.vault_dir,
                proposal,
                approved=True,
                idempotency_key=request.idempotency_key,
            ),
        )

    def task(
        self,
        *,
        action: Literal["list", "read", "create", "advance"] = "list",
        task_id: str | None = None,
        values: Mapping[str, Any] | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read or advance durable work packets without executing next_action."""
        request = context or RequestContext()
        values = dict(values or {})

        def execute() -> dict[str, object] | list[dict[str, object]]:
            if action == "list":
                return list_work_packets(self.vault_dir)
            if not task_id:
                raise ValueError("task_id is required for task read/create/advance")
            if action == "read":
                return read_work_packet(self.vault_dir, task_id)
            if action == "create":
                if request.authority not in {"propose", "apply"}:
                    raise PermissionError("task creation requires propose authority")
                packet_authority = str(values.get("authority", request.authority))
                packet_profile = str(values.get("profile", "standard"))
                if packet_authority not in {"read-only", "propose", "apply"}:
                    raise ValueError("unsupported task authority")
                if packet_profile not in {"standard", "maintenance"}:
                    raise ValueError("unsupported task profile")
                return create_work_packet(
                    self.vault_dir,
                    task_id=task_id,
                    objective=str(values.get("objective", "")),
                    owner=str(values.get("owner", request.actor)),
                    actor=request.actor,
                    scope=list(values.get("scope", [])),
                    authority=cast("Literal['read-only', 'propose', 'apply']", packet_authority),
                    next_action=str(values.get("next_action", "inspect")),
                    profile=cast("Literal['standard', 'maintenance']", packet_profile),
                    idempotency_key=request.idempotency_key,
                )
            if action == "advance":
                if request.authority != "apply":
                    raise PermissionError("task advance requires apply authority")
                return advance_work_packet(
                    self.vault_dir,
                    task_id,
                    actor=request.actor,
                    idempotency_key=request.idempotency_key or task_id,
                    **values,
                )
            raise ValueError(f"unsupported task action: {action}")

        return self._run("task", request, execute)

    def fleet_status(self, *, context: RequestContext | None = None) -> ApplicationEnvelope:
        """Expose the optional fleet capability without a broken endpoint."""
        return self._run(
            "fleet-status",
            context,
            lambda: {
                "status": "unavailable",
                "reason": "optional_fleet_track_not_installed",
                "safe_fallback": "local_fts",
            },
            status="unavailable",
        )

    def receipt(
        self,
        *,
        limit: int = 100,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read bounded, content-free transaction receipts through the boundary."""
        if not 1 <= limit <= 1000:
            raise ValueError("receipt limit must be between 1 and 1000")
        return self._run(
            "receipt",
            context,
            lambda: {"receipts": read_history(self.vault_dir)[-limit:]},
        )

    def _run(
        self,
        operation: str,
        context: RequestContext | None,
        action: Callable[[], Any],
        *,
        status: Literal["ok", "unavailable"] = "ok",
    ) -> ApplicationEnvelope:
        request = context or RequestContext()
        started = time.perf_counter()
        data = action()
        if request.deadline_ms is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if elapsed_ms > request.deadline_ms:
                raise TimeoutError(
                    f"application deadline exceeded after {elapsed_ms:.1f} ms "
                    f"(budget {request.deadline_ms} ms)"
                )
        if not isinstance(data, dict):
            data = {"items": data}
        serializable = json.loads(json.dumps(data, ensure_ascii=False, sort_keys=True, default=str))
        digest = hashlib.sha256(
            json.dumps(serializable, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        receipt = AuditReceipt(
            schema_version="power.receipt.v1",
            operation=operation,
            status=status,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            data_sha256=digest,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )
        if self._audit_hook is not None:
            self._audit_hook(receipt)
        return ApplicationEnvelope(
            operation=operation, status=status, data=serializable, receipt=receipt
        )


__all__ = ["ApplicationEnvelope", "ApplicationService", "AuditReceipt", "RequestContext"]
