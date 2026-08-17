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

from .application_models import (
    SourceListRequest,
    SourceReadRequest,
)
from .capabilities import manifest
from .decision_service import DecisionService
from .memory_api import apply_change, propose_change, read_history
from .searcher import (
    DEFAULT_SEARCH_MODE,
    format_untrusted_search_envelope,
    search_vault,
)
from .source_service import (
    get_graph_projection,
    get_source_stats,
    list_sources,
    read_source,
)
from .task_service import TaskService

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
    actual_capability: str
    source_revision: str | None = None
    schema_version: str = "power.application.v2"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "status": self.status,
            "data": self.data,
            "receipt": self.receipt.as_dict(),
            "request_id": self.receipt.request_id,
            "actual_capability": self.actual_capability,
            "source_revision": self.source_revision,
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
        task_service: TaskService | None = None,
    ) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self._audit_hook = audit_hook
        self._search_fn = search_fn or search_vault
        self.task_service = task_service or TaskService(self.vault_dir)
        self.decision_service = DecisionService(self.vault_dir, task_service=self.task_service)

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
        """Compatibility facade over the canonical TaskService v2 lifecycle."""
        request = context or RequestContext()
        values = dict(values or {})

        def execute() -> dict[str, object] | list[dict[str, object]]:
            if action == "list":
                return [task.model_dump() for task in self.task_service.list_tasks()]
            if not task_id:
                raise ValueError("task_id is required for task read/create/advance")
            if action == "read":
                task = self.task_service.get_task(task_id)
                if task is None:
                    raise FileNotFoundError(f"Task {task_id} not found")
                return task.model_dump()
            if action == "create":
                if request.authority not in {"propose", "apply"}:
                    raise PermissionError("task creation requires propose authority")
                task_authority = str(values.get("authority", request.authority))
                if task_authority not in {"read-only", "propose", "apply"}:
                    raise ValueError("unsupported task authority")
                objective = str(values.get("objective", ""))
                return self.task_service.create_task(
                    task_id=task_id,
                    title=str(values.get("title", objective or task_id))[:256],
                    objective=objective,
                    owner=str(values.get("owner", request.actor)),
                    actor=request.actor,
                    scope=list(values.get("scope", [])),
                    authority=cast("Literal['read-only', 'propose', 'apply']", task_authority),
                    state=cast("Any", values.get("state", "backlog")),
                    source_revision=str(values.get("source_revision", "")),
                    next_action=str(values.get("next_action", "inspect")),
                    kind="maintenance" if values.get("profile") == "maintenance" else "human",
                    required_input=cast("dict[str, Any] | None", values.get("required_input")),
                    idempotency_key=request.idempotency_key,
                ).model_dump()
            if action == "advance":
                if request.authority != "apply":
                    raise PermissionError("task advance requires apply authority")
                legacy_action = values.pop("action", None)
                legacy_state_map = {
                    "resume": "working",
                    "checkpoint": "working",
                    "input-required": "input-required",
                    "complete": "completed",
                    "fail": "failed",
                    "cancel": "canceled",
                }
                new_state = str(values.pop("new_state", legacy_state_map.get(legacy_action, "")))
                if not new_state:
                    raise ValueError("task advance requires new_state or a supported legacy action")
                expected_revision = values.pop("expected_revision", None)
                if expected_revision is None:
                    raise ValueError("task advance requires expected_revision")

                current = self.task_service.get_task(task_id)
                if current is None:
                    raise FileNotFoundError(f"Task {task_id} not found")
                approved = bool(values.pop("approved", False))
                blocker = values.pop("blocker", None)
                required_approval = values.pop("required_approval", None)
                changed_artifacts = values.pop("changed_artifacts", None)
                phase = values.pop("phase", None)

                if legacy_action == "resume" and current.state == "input-required" and not approved:
                    raise PermissionError(
                        "resume requires explicit approval for the requested input"
                    )
                if legacy_action == "checkpoint" and current.state != "working":
                    raise RuntimeError("checkpoint requires a working task")
                if legacy_action in {"input-required", "fail"} and (
                    not isinstance(blocker, str) or not blocker.strip()
                ):
                    raise ValueError(f"{legacy_action} requires a blocker")
                if legacy_action == "cancel" and not approved:
                    raise PermissionError("cancel requires explicit approved=True")

                if legacy_action == "input-required":
                    values["required_input"] = {
                        "blocker": blocker.strip(),
                        "required_approval": required_approval or "caller",
                    }
                elif legacy_action == "fail":
                    values["error_ref"] = blocker.strip()

                model_updates: dict[str, Any] = {}
                if changed_artifacts is not None:
                    merged_artifacts = list(current.artifact_refs)
                    for artifact in changed_artifacts:
                        if artifact not in merged_artifacts:
                            merged_artifacts.append(artifact)
                    model_updates["artifact_refs"] = merged_artifacts
                if phase is not None:
                    external_refs = dict(current.external_refs)
                    external_refs["maintenance_phase"] = str(phase)
                    model_updates["external_refs"] = external_refs
                if model_updates:
                    values["values"] = model_updates
                return self.task_service.transition_task(
                    task_id,
                    new_state=cast("Any", new_state),
                    actor=request.actor,
                    expected_revision=cast("int", expected_revision),
                    receipt_id=cast("str | None", values.pop("receipt_id", None)),
                    completion_postcondition=cast(
                        "str | None", values.pop("completion_postcondition", None)
                    ),
                    completion_artifact_refs=cast(
                        "list[str] | None",
                        values.pop("completion_artifact_refs", changed_artifacts),
                    ),
                    idempotency_key=request.idempotency_key,
                    **values,
                ).model_dump()
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

    def source_list(
        self,
        request: SourceListRequest | None = None,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """List notes in vault with bounded pagination and filtering."""
        return self._run(
            "source.list",
            context,
            lambda: list_sources(self.vault_dir, request).model_dump(),
        )

    def source_read(
        self,
        rel_path: str,
        *,
        max_bytes: int = 2_000_000,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read a note securely with path containment and ETag."""
        req = SourceReadRequest(rel_path=rel_path, max_bytes=max_bytes)
        return self._run(
            "source.read",
            context,
            lambda: read_source(self.vault_dir, req).model_dump(),
        )

    def source_stats(self, *, context: RequestContext | None = None) -> ApplicationEnvelope:
        """Return precomputed aggregate statistics for the vault."""
        return self._run(
            "source.stats",
            context,
            lambda: get_source_stats(self.vault_dir).model_dump(),
        )

    def source_graph(
        self,
        *,
        max_nodes: int = 500,
        focus_path: str | None = None,
        max_depth: int = 2,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Return bounded graph slice for knowledge graph visualization."""
        return self._run(
            "source.graph",
            context,
            lambda: get_graph_projection(
                self.vault_dir,
                max_nodes=max_nodes,
                focus_path=focus_path,
                max_depth=max_depth,
            ).model_dump(),
        )

    def decision_create(
        self,
        *,
        decision_id: str,
        task_id: str,
        title: str,
        requested_by: str | None = None,
        task_revision: int | None = None,
        proposal_id: str | None = None,
        proposal_sha256: str | None = None,
        description: str = "",
        risk_level: str = "medium",
        required_authority: str = "apply",
        allowed_actors: list[str] | None = None,
        response_schema: dict[str, str] | None = None,
        expires_at: str | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Create a typed decision gate bound to one Task v2 revision."""
        request = context or RequestContext(authority="propose")
        if request.authority not in {"propose", "apply"}:
            raise PermissionError("decision creation requires propose authority")
        return self._run(
            "decision.create",
            request,
            lambda: self.decision_service.create_decision(
                decision_id=decision_id,
                task_id=task_id,
                title=title,
                requested_by=requested_by or request.actor,
                task_revision=task_revision,
                proposal_id=proposal_id,
                proposal_sha256=proposal_sha256,
                description=description,
                risk_level=risk_level,
                required_authority=cast("Any", required_authority),
                allowed_actors=allowed_actors,
                response_schema=cast("Any", response_schema),
                expires_at=expires_at,
            ).model_dump(),
        )

    def decision_list(
        self,
        *,
        status: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """List bounded decision gates."""
        return self._run(
            "decision.list",
            context,
            lambda: [
                decision.model_dump()
                for decision in self.decision_service.list_decisions(
                    status=status, task_id=task_id, limit=limit, offset=offset
                )
            ],
        )

    def decision_read(
        self,
        decision_id: str,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read one durable decision gate."""

        def execute() -> dict[str, object]:
            decision = self.decision_service.get_decision(decision_id)
            if decision is None:
                raise FileNotFoundError(f"Decision {decision_id} not found")
            return decision.model_dump()

        return self._run("decision.read", context, execute)

    def decision_resolve(
        self,
        decision_id: str,
        *,
        action: str,
        proposal_sha256: str | None = None,
        input_data: dict[str, Any] | None = None,
        comment: str | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Resolve a decision with actor/authority and binding checks."""
        request = context or RequestContext(authority="apply")
        if request.authority not in {"propose", "apply"}:
            raise PermissionError("decision resolution requires proposal authority")

        def execute() -> dict[str, object]:
            decision, receipt = self.decision_service.resolve_decision(
                decision_id,
                action=cast("Any", action),
                actor=request.actor,
                authority=request.authority,
                proposal_sha256=proposal_sha256,
                input_data=input_data,
                comment=comment,
            )
            return {"decision": decision.model_dump(), "receipt": receipt.model_dump()}

        return self._run("decision.resolve", request, execute)

    def task_create(
        self,
        task_id: str,
        title: str,
        *,
        objective: str = "",
        owner: str = "local",
        assignee: str | None = None,
        state: str = "backlog",
        priority: str = "normal",
        authority: str = "read-only",
        context: RequestContext | None = None,
        **kwargs: Any,
    ) -> ApplicationEnvelope:
        """Create a durable Task v2."""
        request = context or RequestContext(authority="propose")
        if request.authority not in {"propose", "apply"}:
            raise PermissionError("task creation requires propose authority")
        return self._run(
            "task.create",
            request,
            lambda: self.task_service.create_task(
                task_id=task_id,
                title=title,
                objective=objective,
                owner=owner,
                assignee=assignee,
                state=state,  # type: ignore[arg-type]
                priority=priority,  # type: ignore[arg-type]
                authority=authority,  # type: ignore[arg-type]
                actor=request.actor,
                idempotency_key=request.idempotency_key,
                **kwargs,
            ).model_dump(),
        )

    def task_transition(
        self,
        task_id: str,
        new_state: str,
        *,
        expected_revision: int | None = None,
        receipt_id: str | None = None,
        next_action: str | None = None,
        context: RequestContext | None = None,
        **kwargs: Any,
    ) -> ApplicationEnvelope:
        """Advance a Task v2 state."""
        request = context or RequestContext(authority="apply")
        if request.authority != "apply":
            raise PermissionError("task transition requires apply authority")
        return self._run(
            "task.transition",
            request,
            lambda: self.task_service.transition_task(
                task_id,
                new_state=new_state,  # type: ignore[arg-type]
                actor=request.actor,
                expected_revision=expected_revision,
                receipt_id=receipt_id,
                next_action=next_action,
                idempotency_key=request.idempotency_key,
                **kwargs,
            ).model_dump(),
        )

    def task_list(
        self,
        *,
        state: str | None = None,
        owner: str | None = None,
        assignee: str | None = None,
        limit: int = 100,
        offset: int = 0,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """List Task v2 items."""
        return self._run(
            "task.list",
            context,
            lambda: [
                t.model_dump()
                for t in self.task_service.list_tasks(
                    state=state, owner=owner, assignee=assignee, limit=limit, offset=offset
                )
            ],
        )

    def task_read(
        self,
        task_id: str,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read a single Task v2 item."""

        def execute() -> dict[str, object]:
            t = self.task_service.get_task(task_id)
            if not t:
                raise FileNotFoundError(f"Task {task_id} not found")
            return t.model_dump()

        return self._run("task.read", context, execute)

    def task_events(
        self,
        task_id: str,
        *,
        since_sequence: int = 0,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read event stream for a Task v2."""
        return self._run(
            "task.events",
            context,
            lambda: [
                e.model_dump()
                for e in self.task_service.get_events(task_id, since_sequence=since_sequence)
            ],
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
        actual_capability = str(serializable.get("actual_mode", operation))
        raw_source_revision = serializable.get("source_revision")
        source_revision = str(raw_source_revision) if raw_source_revision is not None else None
        return ApplicationEnvelope(
            operation=operation,
            status=status,
            data=serializable,
            receipt=receipt,
            actual_capability=actual_capability,
            source_revision=source_revision,
        )


__all__ = ["ApplicationEnvelope", "ApplicationService", "AuditReceipt", "RequestContext"]
