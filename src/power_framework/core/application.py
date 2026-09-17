"""Stable application boundary shared by local transports.

The application service owns orchestration for the small 3.5.0 core.  CLI and
MCP adapters may format its envelopes, but they do not need to know about
SQLite, cache generations, or proposal files.  Receipts intentionally contain
hashes and identifiers only; note content is never copied into the audit hook.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from .application_models import (
    SourceListRequest,
    SourceReadRequest,
)
from .capabilities import manifest
from .context_compiler import ContextPackCompiler
from .context_contracts import (
    AccessPolicy,
    BudgetClass,
    BudgetProfile,
    ProfileBudgetLayer,
    QueryIntent,
    QueryIntentKind,
    TemporalBoundary,
)
from .decision_service import DecisionService
from .errors import ConflictError
from .healer import heal_vault
from .indexer import run_generate_hierarchical_index, run_generate_sub_index, scan_folder_notes
from .infra_broker import InfraBrokerClient, InfraBrokerClientProtocol, _request_digest
from .infra_models import (
    CAPABILITY_BY_OPERATION,
    InfraCapabilityBlockReceipt,
    InfraExitCategory,
    InfraOperation,
    InfraOperationReceipt,
    InfraReasonCode,
    InfraRequest,
    InfraResponse,
)
from .linter import archive_stale_notes, run_lint_report
from .memory_api import (
    apply_change,
    apply_change_by_id,
    commit_note_change,
    propose_change,
    read_history,
)
from .models import PARA_FOLDERS, MemoryKind, MemoryMetadata, NoteType, OKFMetadata, WritePolicy
from .mutation import execute_vault_mutation
from .parser import build_frontmatter
from .principal import Principal
from .retrieval_planner import RetrievalPlanner
from .search_scope import SearchScopeAccessDeniedError, UnsupportedSearchScopeError
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
from .state_service import ProjectStateService
from .synthesize import synthesize_session_ingest
from .task_models import PowerTask
from .task_service import _INFRA_PROJECTION_TOKEN, TaskService
from .utils import resolve_path_in_vault

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence


logger = logging.getLogger(__name__)


ApplicationAuthority = Literal["read-only", "propose", "apply"]
FailureOutcome = Literal[
    "rejected_before_start",
    "cancelled",
    "failed",
    "completed_after_deadline",
    "completed_after_budget",
]
FailureCode = Literal[
    "permission_denied",
    "invalid_request",
    "not_found",
    "conflict",
    "deadline_exceeded",
    "cancelled",
    "completed_after_deadline",
    "result_budget_exceeded",
    "internal_error",
]

MAX_RESULT_BYTES = 1_000_000
MIN_INFRA_RESULT_BUDGET_BYTES = 4_096
_EMPTY_RESULT_SHA256 = hashlib.sha256(b"").hexdigest()


class DeadlineExceededError(TimeoutError):
    """A request deadline was already exhausted or a read exceeded its budget."""


class CompletedAfterDeadlineError(TimeoutError):
    """A synchronous operation finished after its deadline and may have committed."""


class ResultBudgetExceededError(ValueError):
    """A serialized application result exceeded the caller-lower-only ceiling."""


class CompletedAfterBudgetError(ResultBudgetExceededError):
    """A mutation completed before its result was found to exceed the budget."""


@dataclass(frozen=True)
class RequestContext:
    """Authorization and bounded execution metadata for one use case."""

    actor: str = "local"
    authority: ApplicationAuthority = "read-only"
    idempotency_key: str | None = None
    deadline_ms: int | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    principal: Principal | None = field(default_factory=Principal.local_cli)
    deadline_at: float | None = None
    max_result_bytes: int = MAX_RESULT_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise ValueError("actor must be a non-empty string")
        if self.authority not in {"read-only", "propose", "apply"}:
            raise ValueError("authority must be read-only, propose, or apply")
        if self.idempotency_key is not None and not _TOKEN_PATTERN.fullmatch(self.idempotency_key):
            raise ValueError("idempotency_key must be a safe token")
        if self.deadline_ms is not None and self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")
        if not isinstance(self.request_id, str) or not _TOKEN_PATTERN.fullmatch(self.request_id):
            raise ValueError("request_id must be a safe token")
        if self.principal is None or not isinstance(self.principal, Principal):
            raise ValueError("principal binding is required")
        if self.deadline_at is not None and (
            not isinstance(self.deadline_at, (int, float)) or not math.isfinite(self.deadline_at)
        ):
            raise ValueError("deadline_at must be a finite monotonic timestamp")
        if (
            isinstance(self.max_result_bytes, bool)
            or not isinstance(self.max_result_bytes, int)
            or not 1 <= self.max_result_bytes <= MAX_RESULT_BYTES
        ):
            raise ValueError(f"max_result_bytes must be between 1 and {MAX_RESULT_BYTES}")
        if self.deadline_ms is not None and self.deadline_at is None:
            object.__setattr__(
                self,
                "deadline_at",
                time.monotonic() + (self.deadline_ms / 1000),
            )

    @property
    def result_budget_bytes(self) -> int:
        """Compatibility name for the bounded serialized-result budget."""
        return self.max_result_bytes


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
    outcome: str = "completed"
    principal_ref: str | None = None
    principal_binding: str | None = None
    error_code: str | None = None
    budget_ms: int | None = None
    result_budget_bytes: int | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "status": self.status,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "data_sha256": self.data_sha256,
            "duration_ms": self.duration_ms,
        }
        # Keep the successful power.receipt.v1 wire shape stable. Failure and
        # late-completion receipts opt into the additional bounded evidence.
        if self.status != "ok" or self.outcome != "completed":
            payload.update(
                {
                    "outcome": self.outcome,
                    "principal_ref": self.principal_ref,
                    "principal_binding": self.principal_binding,
                    "error_code": self.error_code,
                    "budget_ms": self.budget_ms,
                    "result_budget_bytes": self.result_budget_bytes,
                }
            )
        return payload


@dataclass(frozen=True)
class ApplicationEnvelope:
    """Versioned JSON-compatible result returned by every application use case."""

    operation: str
    status: Literal["ok", "unavailable"]
    data: dict[str, object]
    receipt: AuditReceipt
    actual_capability: str
    source_revision: str | None = None
    degraded_reason: str | None = None
    schema_version: str = "power.application.v2"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "status": self.status,
            "data": self.data,
            "receipt": self.receipt.as_dict(),
            "request_id": self.receipt.request_id,
            "principal_ref": self.receipt.principal_ref,
            "principal_binding": self.receipt.principal_binding,
            "actual_capability": self.actual_capability,
            "source_revision": self.source_revision,
            "degraded_reason": self.degraded_reason,
        }


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _catalog_page_filename(page: int) -> str:
    """Return the stable generated catalog filename for a one-based page."""
    return "_index.md" if page == 1 else f"_index-{page}.md"


def _read_generated_catalog_page(vault_dir: Path, category: str, page: int) -> str:
    """Read one generated catalog page after the application mutation."""
    category_dir = vault_dir / category
    landing = category_dir / _catalog_page_filename(1)
    if page == 1:
        try:
            return landing.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Generated catalog landing page is missing for {category}"
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("Unable to read the generated catalog landing page") from exc

    try:
        prefix = landing.read_text(encoding="utf-8")[:4096]
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Generated catalog landing page is missing for {category}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise RuntimeError("Unable to read the generated catalog landing page") from exc

    page_count = 1
    for line in prefix.splitlines():
        if line.startswith("x-index-pages:"):
            try:
                page_count = int(line.split(":", 1)[1].strip())
            except (IndexError, ValueError) as exc:
                raise ValueError("Generated catalog page metadata is invalid") from exc
            break
    if page > page_count:
        raise ValueError(f"Catalog page {page} is out of range; available pages: 1-{page_count}")

    target = category_dir / _catalog_page_filename(page)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Catalog page {page} is missing although the landing page declares {page_count}"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Unable to read catalog page {page}") from exc


class ApplicationService:
    """Use-case service for the lean, offline-capable POWER core."""

    def __init__(
        self,
        vault_dir: Path,
        *,
        audit_hook: Callable[[AuditReceipt], None] | None = None,
        search_fn: Callable[..., list[Any]] | None = None,
        task_service: TaskService | None = None,
        decision_service: DecisionService | None = None,
        project_state_service: ProjectStateService | None = None,
        infra_broker: InfraBrokerClientProtocol | None = None,
    ) -> None:
        self.vault_dir = Path(vault_dir).expanduser().resolve()
        self._audit_hook = audit_hook
        self._search_fn = search_fn or partial(search_vault, allow_search_db_override=False)
        self.task_service = task_service or TaskService(self.vault_dir, create_vault=False)
        self.decision_service = decision_service or DecisionService(
            self.vault_dir, task_service=self.task_service
        )
        self.project_state_service: ProjectStateService | None
        if project_state_service is not None:
            self.project_state_service = project_state_service
        else:
            try:
                self.project_state_service = ProjectStateService(
                    self.vault_dir,
                    task_service=self.task_service,
                    decision_service=self.decision_service,
                )
            except Exception:
                self.project_state_service = None
        self.infra_broker = infra_broker or InfraBrokerClient()

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
        if not isinstance(query, str) or not query.strip():
            self._reject_request("retrieve", context, ValueError("Search query cannot be empty"))
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 100
        ):
            self._reject_request(
                "retrieve",
                context,
                ValueError("max_results must be between 1 and 100"),
            )

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

    def compile_context(
        self,
        query: str,
        *,
        intent: str | QueryIntentKind = QueryIntentKind.LOOKUP,
        budget_class: str | BudgetClass = BudgetClass.FAST,
        max_tokens: int | None = None,
        domain_hints: Sequence[str] | None = None,
        project_ids: Sequence[str] | None = None,
        temporal_boundary: TemporalBoundary | str | None = None,
        include_archived: bool = False,
        include_quarantine: bool = False,
        caller_hint: ProfileBudgetLayer | BudgetProfile | None = None,
        access_policy: AccessPolicy | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Compile a server-issued, budget-bounded ContextPack for multi-domain queries."""
        if not isinstance(query, str) or not query.strip():
            self._reject_request(
                "compile_context", context, ValueError("Search query cannot be empty")
            )

        if isinstance(intent, str):
            try:
                intent_kind = QueryIntentKind(intent.lower())
            except ValueError as exc:
                self._reject_request("compile_context", context, exc)
        else:
            intent_kind = intent

        if isinstance(budget_class, str):
            try:
                budget_cls = BudgetClass(budget_class.upper())
            except ValueError as exc:
                self._reject_request("compile_context", context, exc)
        else:
            budget_cls = budget_class

        tb: TemporalBoundary | None = None
        if isinstance(temporal_boundary, str):
            try:
                tb = TemporalBoundary(
                    as_of=date.fromisoformat(temporal_boundary), include_historical=False
                )
            except ValueError as exc:
                self._reject_request("compile_context", context, exc)
        elif isinstance(temporal_boundary, TemporalBoundary):
            tb = temporal_boundary

        intent_kwargs: dict[str, Any] = {
            "query": query.strip(),
            "intent": intent_kind,
            "budget_class": budget_cls,
            "include_archived": include_archived,
            "include_quarantine": include_quarantine,
        }
        if max_tokens is not None:
            intent_kwargs["max_tokens"] = max_tokens
        if domain_hints:
            intent_kwargs["domain_hints"] = list(domain_hints)
        if project_ids:
            self._reject_request(
                "compile_context",
                context,
                UnsupportedSearchScopeError(
                    "project-scoped retrieval is unsupported and fails closed"
                ),
            )
        if tb is not None:
            intent_kwargs["temporal_boundary"] = tb

        query_intent = QueryIntent(**intent_kwargs)

        if include_archived or include_quarantine:
            if (
                access_policy is None
                or access_policy.raw_access != "privileged"
                or access_policy.quarantine_access != "privileged"
            ):
                self._reject_request(
                    "compile_context",
                    context,
                    SearchScopeAccessDeniedError(
                        "privileged search scope requested without a verified privileged AccessPolicy"
                    ),
                )
            effective_policy = access_policy
        elif access_policy is not None:
            effective_policy = access_policy
        else:
            actor = context.principal.ref if context and context.principal else "local_user"
            effective_policy = AccessPolicy._from_authorization_boundary(
                origin="authorization_boundary",
                actor=actor,
                raw_access="none",
                quarantine_access="none",
                redaction="mandatory",
                capability_id="compile_context",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

        def execute() -> dict[str, object]:
            planner = RetrievalPlanner(
                self.vault_dir,
                task_service=self.task_service,
                decision_service=self.decision_service,
                project_state_service=self.project_state_service,
                search_fn=self._search_fn,
            )
            planner_result = planner.plan_and_retrieve(
                query_intent,
                caller_hint=caller_hint,
                access_policy=effective_policy,
            )
            compiler = ContextPackCompiler()
            pack = compiler.compile(
                planner_result,
                query_intent,
                access_policy=effective_policy,
            )
            data = pack.model_dump(mode="json")
            data["actual_capability"] = "compile_context"
            data["source_revision"] = pack.generation_revision
            return data

        return self._run("compile_context", context, execute, mutation=False)

    def propose(
        self,
        rel_path: str,
        content: str,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Persist a reviewable proposal, never the target note."""
        request = self._mutation_context(context, operation="propose")
        if request.authority not in {"propose", "apply"}:
            self._reject_mutation(
                "propose", context, PermissionError("proposal requires propose authority")
            )
        if not isinstance(rel_path, str) or not isinstance(content, str):
            self._reject_request(
                "propose",
                request,
                ValueError("proposal path and content must be strings"),
            )
        estimated_result_bytes = len(content.encode("utf-8")) + 1024
        if estimated_result_bytes > request.max_result_bytes:
            error = ResultBudgetExceededError(
                "proposal result exceeds the application result budget"
            )
            self._emit_failure_receipt("propose", request, error, duration_ms=0)
            raise error
        return self._run(
            "propose",
            request,
            lambda: propose_change(
                self.vault_dir,
                rel_path,
                content,
                idempotency_key=request.idempotency_key,
            ),
            mutation=True,
        )

    def apply(
        self,
        proposal: dict[str, str],
        *,
        approved: bool,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Apply a proposal only with explicit approval authority."""
        request = self._mutation_context(context, operation="apply", require_apply=True)
        if type(approved) is not bool or not approved or request.authority != "apply":
            self._reject_mutation(
                "apply",
                context,
                PermissionError("apply requires explicit approved=True and apply authority"),
            )
        return self._run(
            "apply",
            request,
            lambda: apply_change(
                self.vault_dir,
                proposal,
                approved=True,
                idempotency_key=request.idempotency_key,
            ),
            mutation=True,
        )

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        approved: bool,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Apply a durable content-addressed proposal by ID only."""
        request = self._mutation_context(context, operation="apply", require_apply=True)
        if type(approved) is not bool or not approved or request.authority != "apply":
            self._reject_mutation(
                "apply",
                context,
                PermissionError("apply requires explicit approved=True and apply authority"),
            )
        return self._run(
            "apply",
            request,
            lambda: apply_change_by_id(
                self.vault_dir,
                proposal_id,
                approved=True,
                idempotency_key=request.idempotency_key,
            ),
            mutation=True,
        )

    def _reject_request(
        self,
        operation: str,
        context: RequestContext | None,
        error: Exception,
    ) -> NoReturn:
        """Emit bounded evidence for an admission failure before re-raising it."""
        self._emit_failure_receipt(operation, context, error, duration_ms=0)
        raise error

    def _reject_mutation(
        self,
        operation: str,
        context: RequestContext | None,
        error: PermissionError,
    ) -> NoReturn:
        """Reject a mutation while preserving a bounded failure receipt."""
        self._reject_request(operation, context, error)

    def _mutation_context(
        self,
        context: RequestContext | None,
        *,
        operation: str,
        require_apply: bool = False,
    ) -> RequestContext:
        """Require an explicit, currently valid application mutation context."""
        if context is None:
            self._reject_mutation(
                operation,
                None,
                PermissionError("mutation requires an explicit RequestContext"),
            )
        if context.principal is None or not context.principal.is_valid():
            self._reject_mutation(
                operation,
                context,
                PermissionError("mutation requires a valid, non-expired principal binding"),
            )
        if context.authority not in {"propose", "apply"}:
            self._reject_mutation(
                operation,
                context,
                PermissionError("mutation requires propose or apply authority"),
            )
        if require_apply and context.authority != "apply":
            self._reject_mutation(
                operation,
                context,
                PermissionError("mutation requires apply authority"),
            )
        return context

    def generate_index(self, *, context: RequestContext | None = None) -> ApplicationEnvelope:
        """Regenerate the hierarchical index under the canonical vault lock."""
        request = self._mutation_context(
            context,
            operation="index.generate",
            require_apply=True,
        )
        return self._run(
            "index.generate",
            request,
            lambda: {
                "result": execute_vault_mutation(
                    self.vault_dir, lambda: run_generate_hierarchical_index(self.vault_dir)
                )
            },
            mutation=True,
        )

    def ensure_sub_index(
        self,
        category: str,
        *,
        page: int = 1,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Generate and return one bounded P.A.R.A. catalog page."""
        request = self._mutation_context(
            context,
            operation="index.ensure-sub-index",
            require_apply=True,
        )
        if category not in PARA_FOLDERS:
            self._reject_request(
                "index.ensure-sub-index",
                request,
                ValueError(
                    f"Invalid category: {category}. Must be one of: {', '.join(PARA_FOLDERS)}"
                ),
            )
        if not (self.vault_dir / category).is_dir():
            self._reject_request(
                "index.ensure-sub-index",
                request,
                ValueError(f"Category folder not found: {category}"),
            )
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            self._reject_request(
                "index.ensure-sub-index",
                request,
                ValueError("page must be a positive integer starting at 1"),
            )

        def execute() -> dict[str, object]:
            notes = scan_folder_notes(self.vault_dir).get(category, [])
            if not notes:
                return {"result": f"No notes found in {category}.", "content": ""}

            def mutate() -> dict[str, object]:
                result = run_generate_sub_index(self.vault_dir, category)
                content = _read_generated_catalog_page(self.vault_dir, category, page)
                return {"result": result, "content": content}

            return execute_vault_mutation(self.vault_dir, mutate)

        return self._run("index.ensure-sub-index", request, execute, mutation=True)

    def sync_vault(
        self,
        *,
        fts_only: bool = True,
        accept_dense_loss: bool = False,
        force_rebuild: bool = False,
        allow_partial: bool = False,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Publish an atomic search generation through the application boundary."""
        request = self._mutation_context(context, operation="index.sync", require_apply=True)

        def build() -> dict[str, object]:
            from .generation_index import (
                IndexGenerationError,
                list_invalid_sources,
                sync_vault_atomically,
            )

            invalid_sources = list_invalid_sources(self.vault_dir)
            if invalid_sources and not allow_partial:
                details = "; ".join(
                    f"{rel_path} ({reason})" for rel_path, reason in sorted(invalid_sources.items())
                )
                raise ValueError(
                    "Vault sync failed closed: "
                    f"{len(invalid_sources)} note(s) are excluded and remain unsearchable. "
                    f"Excluded: {details}. Pass allow_partial=True only to publish the valid subset."
                )

            try:
                report = sync_vault_atomically(
                    self.vault_dir,
                    sync_embeddings=not fts_only,
                    force_rebuild=force_rebuild,
                    allow_partial=allow_partial,
                    accept_dense_loss=accept_dense_loss,
                )
            except IndexGenerationError as exc:
                raise RuntimeError(
                    f"Vault sync failed; previous index remains active: {exc}"
                ) from exc

            lines = [
                "=== Vault Sync ===",
                f"Generation: {report.generation_id}",
                f"Mode: {'FTS only' if fts_only else 'FTS + embeddings'}",
                f"Notes scanned: {report.total_scanned}",
                f"Notes indexed: {report.actual_files}",
                f"Notes excluded (invalid metadata): {report.invalid_sources}",
                f"Chunks: {report.actual_chunks}",
            ]
            if report.invalid_sources:
                lines.append("")
                lines.append("Exclusion reasons:")
                lines.extend(
                    f"- {rel_path}: {reason}"
                    for rel_path, reason in sorted(report.excluded_sources.items())
                )
                lines.append(
                    "Excluded notes are not searchable. Run 'power index <vault> --strict' "
                    "to list them, or heal_frontmatter_tool to repair them."
                )
            return {
                "result": "\n".join(lines),
                "generation_id": report.generation_id,
                "actual_files": report.actual_files,
                "actual_chunks": report.actual_chunks,
                "excluded_sources": report.excluded_sources,
            }

        return self._run(
            "index.sync",
            request,
            lambda: execute_vault_mutation(self.vault_dir, build),
            mutation=True,
        )

    def ingest_note(
        self,
        *,
        name: str,
        note_type: str,
        title: str,
        description: str,
        content: str,
        resource: str | None = None,
        tags: list[str] | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Create one validated note and publish all required projections."""
        request = self._mutation_context(
            context,
            operation="memory.ingest-note",
            require_apply=True,
        )
        if not isinstance(name, str) or not isinstance(content, str):
            self._reject_request(
                "memory.ingest-note",
                request,
                ValueError("note name and content must be strings"),
            )
        note_name = name if name.endswith(".md") else f"{name}.md"
        try:
            target_file = resolve_path_in_vault(
                self.vault_dir, note_name, allowed_directories=PARA_FOLDERS
            )
        except ValueError:
            self._reject_request(
                "memory.ingest-note",
                request,
                ValueError(
                    "Invalid note path; use an existing PARA directory and a Markdown filename."
                ),
            )
        if target_file.exists() and request.idempotency_key is None:
            self._reject_request(
                "memory.ingest-note",
                request,
                FileExistsError(f"Note already exists at {note_name}"),
            )

        metadata = OKFMetadata(
            type=NoteType(note_type),
            title=title,
            description=description,
            resource=resource,
            tags=tags or [],
            okf_version="0.2",
            memory=MemoryMetadata(
                kind=MemoryKind.SEMANTIC,
                sources=["power://mcp/ingest_note"],
                evidence=[f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"],
                write_policy=WritePolicy.AGENT_PROPOSED,
            ),
            timestamp=datetime.now(UTC),
        )
        full_content = f"{build_frontmatter(metadata)}\n\n{content}\n"
        idempotency_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "name": name,
                    "note_type": note_type,
                    "title": title,
                    "description": description,
                    "content": content,
                    "resource": resource,
                    "tags": tags or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        def execute() -> dict[str, object]:
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            log_entry = (
                f"\n## [{date_str}] ingest | Created {title}\n"
                f"- **Action:** Created note '{note_name}' of type {note_type} via MCP tool ingest_note.\n"
                f"- **Result:** Saved note to {note_name} and compiled hierarchical index.\n"
            )
            receipt = commit_note_change(
                self.vault_dir,
                note_name,
                full_content,
                require_absent=True,
                allowed_directories=PARA_FOLDERS,
                operation="mcp.ingest_note",
                log_entry=log_entry,
                idempotency_key=request.idempotency_key,
                idempotency_fingerprint=(
                    idempotency_fingerprint if request.idempotency_key is not None else None
                ),
            )
            lint_result = run_lint_report(self.vault_dir)
            return {
                "result": (
                    f"Note '{note_name}' has been successfully ingested!\n"
                    f"{receipt['index_summary']}\n"
                    f"Search projection: {receipt['search_mode']} ({receipt['search_generation']})\n"
                    "Action appended to log.md when the log exists.\n\n"
                    f"Linting Check:\n{lint_result}"
                ),
                "note": note_name,
                "receipt": receipt,
            }

        return self._run("memory.ingest-note", request, execute, mutation=True)

    def synthesize_session(
        self,
        *,
        name: str,
        title: str,
        description: str,
        content: str,
        note_type: str = "Daily Log",
        tags: list[str] | None = None,
        related: list[str] | None = None,
        owner: str | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Create a governed session artifact through the core ingest workflow."""
        request = self._mutation_context(
            context,
            operation="synthesize.session",
            require_apply=True,
        )
        if not isinstance(name, str) or not isinstance(content, str):
            self._reject_request(
                "synthesize.session",
                request,
                ValueError("session name and content must be strings"),
            )
        note_name = name if name.endswith(".md") else f"{name}.md"
        try:
            resolve_path_in_vault(self.vault_dir, note_name, allowed_directories=PARA_FOLDERS)
        except ValueError:
            self._reject_request(
                "synthesize.session",
                request,
                ValueError(
                    "Invalid note path; use an existing PARA directory and a Markdown filename."
                ),
            )
        return self._run(
            "synthesize.session",
            request,
            lambda: {
                "result": synthesize_session_ingest(
                    name=name,
                    title=title,
                    description=description,
                    content=content,
                    note_type=note_type,
                    tags=tags,
                    related=related,
                    owner=owner,
                    vault_path=self.vault_dir,
                    idempotency_key=request.idempotency_key,
                )
            },
            mutation=True,
        )

    def archive_notes(
        self,
        *,
        dry_run: bool = True,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Preview or apply stale-note archival through the core boundary."""
        request = (
            context or RequestContext()
            if dry_run
            else self._mutation_context(
                context,
                operation="maintenance.archive-notes",
                require_apply=True,
            )
        )
        return self._run(
            "maintenance.archive-notes",
            request,
            lambda: {
                "result": (
                    archive_stale_notes(self.vault_dir, dry_run=True)
                    if dry_run
                    else execute_vault_mutation(
                        self.vault_dir,
                        lambda: archive_stale_notes(self.vault_dir, dry_run=False),
                    )
                )
            },
            mutation=not dry_run,
        )

    def heal_frontmatter(
        self,
        *,
        dry_run: bool = True,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Preview or apply frontmatter healing through the core boundary."""
        request = (
            context or RequestContext()
            if dry_run
            else self._mutation_context(
                context,
                operation="maintenance.heal-frontmatter",
                require_apply=True,
            )
        )
        return self._run(
            "maintenance.heal-frontmatter",
            request,
            lambda: {
                "result": (
                    heal_vault(self.vault_dir, dry_run=True)
                    if dry_run
                    else execute_vault_mutation(
                        self.vault_dir,
                        lambda: heal_vault(self.vault_dir, dry_run=False),
                    )
                )
            },
            mutation=not dry_run,
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
        request = (
            self._mutation_context(
                context,
                operation="task",
                require_apply=action == "advance",
            )
            if action in {"create", "advance"}
            else context or RequestContext()
        )
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
                authority_rank = {"read-only": 0, "propose": 1, "apply": 2}
                if authority_rank[task_authority] > authority_rank[request.authority]:
                    raise PermissionError("task authority cannot exceed request authority")
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
                if (
                    expected_revision is None
                    or isinstance(expected_revision, bool)
                    or not isinstance(expected_revision, int)
                    or expected_revision < 1
                ):
                    raise ValueError("task advance requires a positive expected_revision")

                current = self.task_service.get_task(task_id)
                if current is None:
                    raise FileNotFoundError(f"Task {task_id} not found")
                approved_value = values.pop("approved", False)
                if not isinstance(approved_value, bool):
                    raise ValueError("approved must be a boolean")
                approved = approved_value
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
                supplied_nested_values = values.get("values")
                if isinstance(supplied_nested_values, dict) and any(
                    key.startswith("infra_")
                    for key in supplied_nested_values
                    if isinstance(key, str)
                ):
                    raise PermissionError(
                        "Infrastructure task references are not writable through task facade"
                    )
                receipt_id_value = cast("str | None", values.pop("receipt_id", None))
                completion_postcondition_value = cast(
                    "str | None", values.pop("completion_postcondition", None)
                )
                completion_artifact_refs_value = cast(
                    "list[str] | None",
                    values.pop("completion_artifact_refs", changed_artifacts),
                )
                transition_kwargs: dict[str, Any] = {}
                public_transition_fields = {
                    "next_action",
                    "assignee",
                    "required_input",
                    "open_gates",
                    "error_ref",
                    "max_attempts",
                    "retry_at",
                    "lease_owner",
                    "lease_expires_at",
                    "heartbeat_at",
                    "execution_state",
                    "dead_letter_reason",
                    "due_at",
                    "values",
                }
                for field_name in public_transition_fields:
                    if field_name in values:
                        transition_kwargs[field_name] = values.pop(field_name)
                if values:
                    raise ValueError(
                        "task transition contains unsupported fields: " + ", ".join(sorted(values))
                    )
                return self.task_service.transition_task(
                    task_id,
                    new_state=cast("Any", new_state),
                    actor=request.actor,
                    expected_revision=expected_revision,
                    receipt_id=receipt_id_value,
                    completion_postcondition=completion_postcondition_value,
                    completion_artifact_refs=completion_artifact_refs_value,
                    idempotency_key=request.idempotency_key,
                    **transition_kwargs,
                ).model_dump()
            raise ValueError(f"unsupported task action: {action}")

        return self._run(
            "task",
            request,
            execute,
            mutation=action in {"create", "advance"},
        )

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

    def infra_action(
        self,
        request: InfraRequest,
        *,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Execute one typed broker action through the standard application envelope.

        The application boundary deliberately has no SSH/rsync fallback. A
        missing broker remains a typed capability block. An optional Task
        binding is checked against its current revision before the broker call;
        a broker receipt is recorded as an external reference and never treated
        as a canonical Task completion receipt.
        """
        if not isinstance(request, InfraRequest):
            raise TypeError("infra_action requires an InfraRequest")
        sanitized_context = replace(context, idempotency_key=None) if context is not None else None
        broker_request = request
        task_claim_revision: int | None = None
        new_task_claimed = False
        if request.task_id and request.operation is InfraOperation.VERIFY:
            execution_context = self._mutation_context(
                sanitized_context,
                operation="infra.verify",
                require_apply=True,
            )
            execution_context = replace(execution_context, idempotency_key=None)
            if self._deadline_expired(execution_context):
                self._reject_request(
                    "infra.verify",
                    execution_context,
                    DeadlineExceededError("application deadline exceeded before task verify"),
                )
            current_task = self.task_service.get_task(request.task_id)
            if current_task is None:
                self._reject_request(
                    "infra.verify",
                    execution_context,
                    FileNotFoundError(f"Task {request.task_id} not found"),
                )
            if current_task.is_terminal():
                self._reject_request(
                    "infra.verify",
                    execution_context,
                    ConflictError("terminal tasks cannot be verified"),
                )
            if (
                current_task.external_refs.get("infra_operation") != InfraOperation.REPLICATE.value
                or current_task.external_refs.get("infra_run_id") != request.run_id
                or current_task.external_refs.get("infra_manifest_digest") in {None, "none"}
            ):
                self._reject_request(
                    "infra.verify",
                    execution_context,
                    ConflictError("task verify must bind the active replicate run"),
                )
            if current_task.revision != request.expected_revision:
                self._reject_request(
                    "infra.verify",
                    execution_context,
                    ConflictError("task revision changed before verify admission"),
                )
            broker_request = request
        elif request.task_id:
            execution_context = self._mutation_context(
                sanitized_context,
                operation=f"infra.{request.operation.value}",
                require_apply=True,
            )
            execution_context = replace(execution_context, idempotency_key=None)
            if execution_context.max_result_bytes < MIN_INFRA_RESULT_BUDGET_BYTES:
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    ResultBudgetExceededError("infrastructure result budget is too small"),
                )
            if self._deadline_expired(execution_context):
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    DeadlineExceededError("application deadline exceeded before task claim"),
                )
            current_task = self.task_service.get_task(request.task_id)
            if current_task is None:
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    FileNotFoundError(f"Task {request.task_id} not found"),
                )
            if current_task.is_terminal():
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    ConflictError("terminal tasks cannot start infrastructure execution"),
                )
            if current_task.state == "backlog":
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    ConflictError("task-bound infrastructure action requires a ready task"),
                )
            if request.idempotency_key is None:
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    ValueError("task-bound infrastructure action requires idempotency_key"),
                )
            claim_key = (
                "infra-claim-" + hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()
            )
            intent_digest = _request_digest(request)
            active_claim_key = current_task.external_refs.get("infra_claim_key_ref")
            active_claim_intent = current_task.external_refs.get("infra_claim_intent_digest")
            if (
                active_claim_key is not None
                and current_task.execution_state in {"leased", "running"}
                and (active_claim_key != claim_key or active_claim_intent != intent_digest)
            ):
                self._reject_request(
                    f"infra.{request.operation.value}",
                    execution_context,
                    ConflictError("active infrastructure claim requires reconciliation"),
                )
            prior_claim = self._find_infra_task_claim(request.task_id, claim_key, intent_digest)
            if prior_claim is not None:
                if current_task.revision == prior_claim.revision:
                    claimed_revision = prior_claim.revision
                elif (
                    current_task.revision == prior_claim.revision + 1
                    and self._last_task_event_is_infra_projection(request.task_id, intent_digest)
                ):
                    # The prior call projected a bounded block. Re-admit the
                    # same intent at the new CAS revision; the broker's own
                    # idempotency key remains unchanged and excludes Task
                    # metadata, so this cannot create a second replicate.
                    claimed_revision = current_task.revision
                else:
                    self._reject_request(
                        f"infra.{request.operation.value}",
                        execution_context,
                        ConflictError("task claim has already advanced; reconcile before retry"),
                    )
                broker_request = request.model_copy(update={"expected_revision": claimed_revision})
            else:
                if current_task.revision != request.expected_revision:
                    self._reject_request(
                        f"infra.{request.operation.value}",
                        execution_context,
                        ConflictError("task revision changed before broker admission"),
                    )
                if self._deadline_expired(execution_context):
                    self._reject_request(
                        f"infra.{request.operation.value}",
                        execution_context,
                        DeadlineExceededError("application deadline exceeded before task claim"),
                    )
                claimed_task = self.task_service.transition_task(
                    request.task_id,
                    new_state=current_task.state,
                    actor=execution_context.actor,
                    expected_revision=request.expected_revision,
                    idempotency_key=claim_key,
                    _projection_token=_INFRA_PROJECTION_TOKEN,
                    values={
                        "execution_state": "leased",
                        "external_refs": {
                            **{
                                key: value
                                for key, value in current_task.external_refs.items()
                                if not key.startswith("infra_")
                            },
                            "infra_operation": request.operation.value,
                            "infra_claim_key_ref": claim_key,
                            "infra_claim_intent_digest": intent_digest,
                        },
                    },
                )
                task_claim_revision = claimed_task.revision
                new_task_claimed = True
                if self._deadline_expired(execution_context):
                    self._release_unstarted_task_claim(
                        request,
                        claimed_task.revision,
                        execution_context,
                    )
                    self._reject_request(
                        f"infra.{request.operation.value}",
                        execution_context,
                        DeadlineExceededError("application deadline exceeded during task claim"),
                    )
                broker_request = request.model_copy(
                    update={"expected_revision": claimed_task.revision}
                )
        elif request.operation == InfraOperation.REPLICATE:
            execution_context = self._mutation_context(
                sanitized_context,
                operation="infra.replicate",
                require_apply=True,
            )
            execution_context = replace(execution_context, idempotency_key=None)
        else:
            execution_context = sanitized_context or RequestContext()
        if (
            request.task_id is None
            and execution_context.max_result_bytes < MIN_INFRA_RESULT_BUDGET_BYTES
        ):
            self._reject_request(
                f"infra.{request.operation.value}",
                execution_context,
                ResultBudgetExceededError("infrastructure result budget is too small"),
            )

        def execute() -> dict[str, object]:
            if new_task_claimed and self._deadline_expired(execution_context):
                if task_claim_revision is not None:
                    self._release_unstarted_task_claim(
                        request,
                        task_claim_revision,
                        execution_context,
                    )
                raise DeadlineExceededError("application deadline exceeded before broker call")
            status_method = getattr(self.infra_broker, "status", None)
            response = (
                status_method()
                if broker_request.operation is InfraOperation.STATUS and callable(status_method)
                else self.infra_broker.execute(broker_request)
            )
            if not isinstance(response, InfraResponse):
                raise ValueError("infra broker returned an invalid response object")
            if (
                response.operation is not broker_request.operation
                or response.target != broker_request.target
                or response.profile != broker_request.profile
                or response.task_id != broker_request.task_id
                or response.request_digest != _request_digest(broker_request)
            ):
                raise ValueError("infra broker response is not bound to the request")
            if new_task_claimed and self._deadline_expired(execution_context):
                committed = isinstance(
                    response.receipt, InfraOperationReceipt
                ) and response.receipt.exit_category in {
                    InfraExitCategory.SUCCESS,
                    InfraExitCategory.REPLAY,
                }
                uncertain = isinstance(
                    response.receipt, InfraCapabilityBlockReceipt
                ) and response.receipt.reason_code in {
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    InfraReasonCode.OPERATION_IN_FLIGHT,
                }
                if broker_request.operation is InfraOperation.REPLICATE:
                    if committed or uncertain:
                        # Let the projection persist the broker evidence; the
                        # surrounding _run call will then report the late
                        # mutation as CompletedAfterDeadline.
                        pass
                    else:
                        if task_claim_revision is not None:
                            self._release_unstarted_task_claim(
                                request,
                                task_claim_revision,
                                execution_context,
                            )
                        raise DeadlineExceededError(
                            "application deadline exceeded before broker result projection"
                        )
                else:
                    if task_claim_revision is not None:
                        self._release_unstarted_task_claim(
                            request,
                            task_claim_revision,
                            execution_context,
                        )
                    raise DeadlineExceededError(
                        "application deadline exceeded before broker result projection"
                    )
            projection: dict[str, object] | None = None
            if broker_request.task_id:
                try:
                    if isinstance(response.receipt, InfraCapabilityBlockReceipt):
                        projection = self._project_infra_block(
                            broker_request, response, execution_context
                        )
                    else:
                        projection = self._project_infra_receipt(
                            broker_request, response, execution_context
                        )
                except ConflictError:
                    projection = (
                        self._retry_infra_block_projection(
                            broker_request, response, execution_context
                        )
                        if isinstance(response.receipt, InfraCapabilityBlockReceipt)
                        else self._reconcile_infra_task_projection(
                            broker_request.task_id, response.receipt.receipt_id
                        )
                    )
            receipt = response.receipt
            result_state = response.status.value
            if isinstance(receipt, InfraCapabilityBlockReceipt):
                if receipt.reason_code is InfraReasonCode.REQUEST_INPUT_MISSING:
                    result_state = "input-required"
                elif receipt.reason_code is InfraReasonCode.APPROVAL_REQUIRED:
                    result_state = "auth-required"
                else:
                    result_state = "blocked"
                execution_outcome = receipt.reason_code.value
            else:
                execution_outcome = receipt.exit_category.value
            if projection is not None:
                result_state = str(projection["state"])
            result: dict[str, object] = {
                "infra": response.model_dump(mode="json"),
                "state": result_state,
                "task_state": projection.get("state") if projection is not None else None,
                "execution_state": (
                    projection.get("execution_state") if projection is not None else None
                ),
                "execution_outcome": execution_outcome,
                "required_input": (
                    {"target": "target", "profile": "profile"}
                    if isinstance(receipt, InfraCapabilityBlockReceipt)
                    and receipt.reason_code is InfraReasonCode.REQUEST_INPUT_MISSING
                    else None
                ),
                "open_gates": (
                    [receipt.required_capability]
                    if isinstance(receipt, InfraCapabilityBlockReceipt)
                    and receipt.reason_code
                    not in {
                        InfraReasonCode.REQUEST_INPUT_MISSING,
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        InfraReasonCode.OPERATION_IN_FLIGHT,
                    }
                    else []
                ),
                "error_ref": (
                    receipt.receipt_id if isinstance(receipt, InfraCapabilityBlockReceipt) else None
                ),
                "receipt_ids": [receipt.receipt_id],
                "actual_capability": (
                    receipt.required_capability
                    if isinstance(receipt, InfraCapabilityBlockReceipt)
                    else CAPABILITY_BY_OPERATION[broker_request.operation]
                ),
                "source_revision": (
                    receipt.policy_revision
                    if isinstance(receipt, (InfraCapabilityBlockReceipt, InfraOperationReceipt))
                    else None
                ),
                "degraded_reason": (
                    receipt.reason_code.value
                    if isinstance(receipt, InfraCapabilityBlockReceipt)
                    else None
                ),
            }
            if projection is not None:
                result["task_projection"] = projection
            return result

        return self._run(
            f"infra.{request.operation.value}",
            execution_context,
            execute,
            mutation=request.operation is InfraOperation.REPLICATE or request.task_id is not None,
        )

    def _release_unstarted_task_claim(
        self,
        request: InfraRequest,
        claimed_revision: int,
        context: RequestContext,
    ) -> None:
        """Clear a lease when the application deadline expires before broker start."""

        task_id = request.task_id
        if task_id is None:
            return
        current = self.task_service.get_task(task_id)
        if current is None or current.revision != claimed_revision:
            return
        cleanup_key = (
            "infra-deadline-" + hashlib.sha256(_request_digest(request).encode("utf-8")).hexdigest()
        )
        self.task_service.transition_task(
            task_id,
            new_state=current.state,
            actor=context.actor,
            expected_revision=claimed_revision,
            idempotency_key=cleanup_key,
            values={
                "execution_state": "none",
                "external_refs": {
                    **current.external_refs,
                    "infra_claim_aborted": "deadline-before-broker",
                },
            },
            _projection_token=_INFRA_PROJECTION_TOKEN,
        )

    def _find_infra_task_claim(
        self, task_id: str, claim_key: str, intent_digest: str
    ) -> PowerTask | None:
        """Find a prior deterministic Task claim before comparing the caller revision."""

        for event in reversed(self.task_service.get_events(task_id)):
            if event.event_type != "state_transition":
                continue
            if event.payload.get("idempotency_key") != claim_key:
                continue
            result = event.payload.get("result")
            if not isinstance(result, dict):
                continue
            try:
                candidate = PowerTask.model_validate(result)
            except (TypeError, ValueError):
                continue
            if (
                candidate.external_refs.get("infra_claim_key_ref") == claim_key
                and candidate.external_refs.get("infra_claim_intent_digest") == intent_digest
            ):
                return candidate
        return None

    def _last_task_event_is_infra_projection(self, task_id: str, intent_digest: str) -> bool:
        """Recognize only the adapter's own immediately preceding projection."""

        events = self.task_service.get_events(task_id)
        if not events:
            return False
        result = events[-1].payload.get("result")
        if not isinstance(result, dict):
            return False
        external_refs = result.get("external_refs")
        return (
            str(events[-1].payload.get("idempotency_key", "")).startswith(
                ("infra-result-", "infra-resolve-", "infra-deadline-")
            )
            and isinstance(external_refs, dict)
            and external_refs.get("infra_claim_intent_digest") == intent_digest
        )

    def _project_infra_block(
        self,
        request: InfraRequest,
        response: InfraResponse,
        context: RequestContext,
        *,
        store_lock_fallback: bool = False,
    ) -> dict[str, object]:
        """Reference a block receipt without inventing a Task state."""
        task_id = request.task_id
        if task_id is None:
            raise ValueError("task-bound infrastructure block requires task_id")
        if request.expected_revision is None and not store_lock_fallback:
            raise ValueError("task-bound infrastructure action requires expected_revision")
        if context.authority != "apply":
            raise PermissionError("task-bound infrastructure action requires apply authority")
        receipt = response.receipt
        if not isinstance(receipt, InfraCapabilityBlockReceipt):
            return {}
        current = self.task_service.get_task(task_id)
        if current is None:
            raise FileNotFoundError(f"Task {task_id} not found")
        claim_key = (
            "infra-claim-" + hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()
            if request.idempotency_key is not None
            else ""
        )
        claim_intent_digest = _request_digest(request)
        if request.operation is InfraOperation.VERIFY:
            claim_key = current.external_refs.get("infra_claim_key_ref", "")
            claim_intent_digest = current.external_refs.get("infra_claim_intent_digest", "")
            if (
                current.external_refs.get("infra_operation") != InfraOperation.REPLICATE.value
                or current.external_refs.get("infra_run_id") != request.run_id
                or current.external_refs.get("infra_manifest_digest") in {None, "none"}
            ):
                return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
        if store_lock_fallback:
            if request.idempotency_key is None:
                return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
            if (
                current.external_refs.get("infra_claim_key_ref") != claim_key
                or current.external_refs.get("infra_claim_intent_digest") != claim_intent_digest
            ):
                return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
        if receipt.reason_code == InfraReasonCode.REQUEST_INPUT_MISSING:
            desired_state = "input-required"
            required_input: dict[str, Any] | None = {
                "required_fields": ["target", "profile"],
            }
            execution_state = "none"
        elif receipt.reason_code == InfraReasonCode.APPROVAL_REQUIRED:
            desired_state = "auth-required"
            required_input = None
            execution_state = "none"
        elif receipt.reason_code in {
            InfraReasonCode.UNKNOWN_COMPLETION,
            InfraReasonCode.OPERATION_IN_FLIGHT,
        }:
            # The external outcome is unknown; do not falsely say that a
            # capability is absent or transition a working task to blocked.
            desired_state = current.state
            required_input = None
            execution_state = "leased"
        else:
            desired_state = "blocked"
            required_input = None
            execution_state = (
                "waiting-network"
                if receipt.reason_code == InfraReasonCode.NETWORK_UNAVAILABLE
                else "none"
            )
        intent_digest = _request_digest(request)
        projection_key = (
            "infra-result-"
            + hashlib.sha256(f"{intent_digest}:{receipt.reason_code.value}".encode()).hexdigest()
        )
        prior_projection = self._find_infra_task_projection(task_id, projection_key)
        if prior_projection is not None:
            if not (
                receipt.run_id
                and receipt.source_manifest_digest
                and current.external_refs.get("infra_run_id") in {None, "none"}
            ):
                return prior_projection
            projection_key = (
                "infra-resolve-"
                + hashlib.sha256(
                    f"{intent_digest}:{receipt.run_id}:{receipt.source_manifest_digest}".encode()
                ).hexdigest()
            )
            prior_resolution = self._find_infra_task_projection(task_id, projection_key)
            if prior_resolution is not None:
                return prior_resolution
        if current.state in {"completed", "failed", "canceled", "rejected"}:
            return {
                "task_id": task_id,
                "state": current.state,
                "execution_state": current.execution_state,
                "receipt_id": receipt.receipt_id,
                "projection": "terminal-task-fenced",
            }
        transition_allowed = current.can_transition_to(cast("Any", desired_state))
        new_state = desired_state if transition_allowed else current.state
        open_gates = list(current.open_gates)
        if (
            isinstance(receipt, InfraCapabilityBlockReceipt)
            and receipt.reason_code
            not in {InfraReasonCode.UNKNOWN_COMPLETION, InfraReasonCode.OPERATION_IN_FLIGHT}
            and receipt.required_capability not in open_gates
        ):
            open_gates.append(receipt.required_capability)
        values: dict[str, Any] = {
            "execution_state": execution_state,
            "required_input": required_input,
            "external_refs": {
                **current.external_refs,
                "infra_reason_code": receipt.reason_code.value,
                "infra_broker_status": receipt.broker_status,
                "infra_run_id": receipt.run_id or "none",
                "infra_manifest_digest": receipt.source_manifest_digest or "none",
                "infra_profile_id": request.profile or "none",
                "infra_target_id": request.target or "none",
                "infra_block_receipt_id": receipt.receipt_id,
            },
        }
        if not transition_allowed and desired_state != current.state:
            values["external_refs"]["infra_projection_state"] = "state-preserved-illegal-transition"
        try:
            self.task_service.transition_task(
                task_id,
                new_state=new_state,  # type: ignore[arg-type]
                actor=context.actor,
                expected_revision=request.expected_revision,
                receipt_id=receipt.receipt_id,
                idempotency_key=projection_key,
                open_gates=open_gates,
                error_ref=receipt.receipt_id,
                _projection_token=_INFRA_PROJECTION_TOKEN,
                values=values,
            )
        except ValueError:
            prior_projection = self._find_infra_task_projection(task_id, projection_key)
            if prior_projection is None:
                raise
            return prior_projection
        return {
            "task_id": task_id,
            "state": new_state,
            "execution_state": execution_state,
            "receipt_id": receipt.receipt_id,
            "projection": (
                "state-preserved-illegal-transition"
                if not transition_allowed and desired_state != current.state
                else "applied"
            ),
        }

    def _reconcile_infra_task_projection(self, task_id: str, receipt_id: str) -> dict[str, object]:
        """Return a bounded reconciliation marker when Task CAS loses a race."""

        current = self.task_service.get_task(task_id)
        if current is None:
            raise FileNotFoundError(f"Task {task_id} not found")
        return {
            "task_id": task_id,
            "state": current.state,
            "execution_state": current.execution_state,
            "receipt_id": receipt_id,
            "projection": "cas-conflict-reconcile-required",
        }

    def _retry_infra_block_projection(
        self,
        request: InfraRequest,
        response: InfraResponse,
        context: RequestContext,
    ) -> dict[str, object]:
        """Retry a block projection against the latest Task revision before reconciling."""

        task_id = request.task_id
        if task_id is None:
            raise ValueError("infra block projection requires task_id")
        for _attempt in range(3):
            current = self.task_service.get_task(task_id)
            if current is None:
                raise FileNotFoundError(f"Task {task_id} not found")
            updated_request = request.model_copy(update={"expected_revision": current.revision})
            try:
                return self._project_infra_block(updated_request, response, context)
            except ConflictError:
                continue
        current = self.task_service.get_task(task_id)
        if current is None:
            raise FileNotFoundError(f"Task {task_id} not found")
        with self.task_service.store.lock():
            current = self.task_service.get_task(task_id)
            if current is None:
                raise FileNotFoundError(f"Task {task_id} not found")
            return self._project_infra_block(
                request.model_copy(update={"expected_revision": current.revision}),
                response,
                context,
                store_lock_fallback=True,
            )

    def _find_infra_task_projection(
        self, task_id: str, projection_key: str
    ) -> dict[str, object] | None:
        """Replay an adapter projection without creating another Task revision."""

        for event in reversed(self.task_service.get_events(task_id)):
            if event.event_type != "state_transition":
                continue
            if event.payload.get("idempotency_key") != projection_key:
                continue
            result = event.payload.get("result")
            if not isinstance(result, dict):
                continue
            try:
                task = PowerTask.model_validate(result)
            except (TypeError, ValueError):
                continue
            return {
                "task_id": task_id,
                "state": task.state,
                "execution_state": task.execution_state,
                "receipt_id": next(
                    (
                        receipt_id
                        for receipt_id in reversed(task.receipt_ids)
                        if receipt_id.startswith(("ibr_", "ir_"))
                    ),
                    "unknown",
                ),
                "projection": "replay",
            }
        return None

    def _project_infra_receipt(
        self,
        request: InfraRequest,
        response: InfraResponse,
        context: RequestContext,
    ) -> dict[str, object]:
        """Attach an infra receipt while leaving Task completion governed."""

        task_id = request.task_id
        if task_id is None or request.expected_revision is None:
            raise ValueError("task-bound infrastructure receipt requires task binding")
        receipt = response.receipt
        if not isinstance(receipt, InfraOperationReceipt):
            return {}
        intent_digest = _request_digest(request)
        projection_key = (
            "infra-result-"
            + hashlib.sha256(
                f"{intent_digest}:{request.operation.value}:receipt".encode()
            ).hexdigest()
        )
        if request.idempotency_key is None:
            return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
        claim_key = (
            "infra-claim-" + hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()
        )
        for _attempt in range(3):
            current = self.task_service.get_task(task_id)
            if current is None:
                raise FileNotFoundError(f"Task {task_id} not found")
            task_claim_key = claim_key
            task_claim_intent_digest = intent_digest
            if request.operation is InfraOperation.VERIFY:
                task_claim_key = current.external_refs.get("infra_claim_key_ref", "")
                task_claim_intent_digest = current.external_refs.get(
                    "infra_claim_intent_digest", ""
                )
                if (
                    current.external_refs.get("infra_operation") != InfraOperation.REPLICATE.value
                    or current.external_refs.get("infra_run_id") != request.run_id
                    or current.external_refs.get("infra_manifest_digest") in {None, "none"}
                ):
                    return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
            prior_projection = self._find_infra_task_projection(task_id, projection_key)
            if prior_projection is not None:
                return prior_projection
            if (
                current.external_refs.get("infra_claim_key_ref") != task_claim_key
                or current.external_refs.get("infra_claim_intent_digest")
                != task_claim_intent_digest
            ):
                return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
            if current.state in {"completed", "failed", "canceled", "rejected"}:
                return {
                    "task_id": task_id,
                    "state": current.state,
                    "execution_state": current.execution_state,
                    "receipt_id": receipt.receipt_id,
                    "projection": "terminal-task-fenced",
                }
            execution_state = "running" if request.operation is InfraOperation.REPLICATE else "none"
            external_refs = {
                **current.external_refs,
                "infra_policy_revision": receipt.policy_revision,
            }
            if request.operation is InfraOperation.REPLICATE:
                external_refs.update(
                    {
                        "infra_receipt_id": receipt.receipt_id,
                        "infra_run_id": receipt.run_id or "none",
                        "infra_manifest_digest": receipt.source_manifest_digest or "none",
                        "infra_profile_id": receipt.profile_id or "none",
                        "infra_target_id": receipt.target_id or "none",
                    }
                )
            elif request.operation is InfraOperation.VERIFY:
                external_refs.update(
                    {
                        "infra_verify_receipt_id": receipt.receipt_id,
                        "infra_verify_run_id": receipt.run_id or "none",
                        "infra_verify_manifest_digest": receipt.source_manifest_digest or "none",
                        "infra_verify_profile_id": receipt.profile_id or "none",
                        "infra_verify_target_id": receipt.target_id or "none",
                        "infra_verify_status": receipt.verification_result or "unknown",
                    }
                )
            else:
                external_refs.update(
                    {
                        "infra_receipt_id": receipt.receipt_id,
                        "infra_run_id": receipt.run_id or "none",
                        "infra_manifest_digest": receipt.source_manifest_digest or "none",
                        "infra_profile_id": receipt.profile_id or "none",
                        "infra_target_id": receipt.target_id or "none",
                    }
                )
            try:
                updated = self.task_service.transition_task(
                    task_id,
                    new_state=current.state,
                    actor=context.actor,
                    expected_revision=current.revision,
                    receipt_id=receipt.receipt_id,
                    idempotency_key=projection_key,
                    _projection_token=_INFRA_PROJECTION_TOKEN,
                    values={"execution_state": execution_state, "external_refs": external_refs},
                )
            except ConflictError:
                continue
            return {
                "task_id": task_id,
                "state": updated.state,
                "execution_state": updated.execution_state,
                "receipt_id": receipt.receipt_id,
                "projection": "applied-after-cas-retry" if _attempt else "applied",
            }
        current = self.task_service.get_task(task_id)
        if current is None:
            raise FileNotFoundError(f"Task {task_id} not found")
        task_claim_key = claim_key
        task_claim_intent_digest = intent_digest
        if request.operation is InfraOperation.VERIFY:
            task_claim_key = current.external_refs.get("infra_claim_key_ref", "")
            task_claim_intent_digest = current.external_refs.get("infra_claim_intent_digest", "")
        if (
            current.external_refs.get("infra_claim_key_ref") != task_claim_key
            or current.external_refs.get("infra_claim_intent_digest") != task_claim_intent_digest
        ):
            return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
        fallback_refs = {
            "infra_policy_revision": receipt.policy_revision,
            "infra_projection_state": "applied-under-store-lock",
        }
        if request.operation is InfraOperation.REPLICATE:
            fallback_refs.update(
                {
                    "infra_receipt_id": receipt.receipt_id,
                    "infra_run_id": receipt.run_id or "none",
                    "infra_manifest_digest": receipt.source_manifest_digest or "none",
                    "infra_profile_id": receipt.profile_id or "none",
                    "infra_target_id": receipt.target_id or "none",
                }
            )
        elif request.operation is InfraOperation.VERIFY:
            fallback_refs.update(
                {
                    "infra_verify_receipt_id": receipt.receipt_id,
                    "infra_verify_run_id": receipt.run_id or "none",
                    "infra_verify_manifest_digest": receipt.source_manifest_digest or "none",
                    "infra_verify_profile_id": receipt.profile_id or "none",
                    "infra_verify_target_id": receipt.target_id or "none",
                    "infra_verify_status": receipt.verification_result or "unknown",
                }
            )
        else:
            fallback_refs.update(
                {
                    "infra_receipt_id": receipt.receipt_id,
                    "infra_run_id": receipt.run_id or "none",
                    "infra_manifest_digest": receipt.source_manifest_digest or "none",
                    "infra_profile_id": receipt.profile_id or "none",
                    "infra_target_id": receipt.target_id or "none",
                }
            )
        try:
            updated = self.task_service.transition_task(
                task_id,
                new_state=current.state,
                actor=context.actor,
                expected_revision=None,
                receipt_id=receipt.receipt_id,
                idempotency_key=projection_key,
                required_claim_key=task_claim_key,
                required_claim_intent_digest=task_claim_intent_digest,
                external_ref_updates=fallback_refs,
                _projection_token=_INFRA_PROJECTION_TOKEN,
                values={
                    "execution_state": (
                        "running" if request.operation is InfraOperation.REPLICATE else "none"
                    ),
                },
            )
        except ConflictError:
            return self._reconcile_infra_task_projection(task_id, receipt.receipt_id)
        except ValueError:
            prior_projection = self._find_infra_task_projection(task_id, projection_key)
            if prior_projection is None:
                raise
            return prior_projection
        return {
            "task_id": task_id,
            "state": updated.state,
            "execution_state": updated.execution_state,
            "receipt_id": receipt.receipt_id,
            "projection": "applied-under-store-lock",
        }

    def receipt(
        self,
        *,
        limit: int = 100,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Read bounded, content-free transaction receipts through the boundary."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            self._reject_request(
                "receipt",
                context,
                ValueError("receipt limit must be between 1 and 1000"),
            )
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
        try:
            req = SourceReadRequest(rel_path=rel_path, max_bytes=max_bytes)
        except (TypeError, ValueError) as error:
            self._reject_request("source.read", context, error)
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
        request = self._mutation_context(context, operation="decision.create")
        if request.authority not in {"propose", "apply"}:
            self._reject_mutation(
                "decision.create",
                context,
                PermissionError("decision creation requires propose authority"),
            )
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
            mutation=True,
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
        request = self._mutation_context(context, operation="decision.resolve")
        if request.authority not in {"propose", "apply"}:
            self._reject_mutation(
                "decision.resolve",
                context,
                PermissionError("decision resolution requires proposal authority"),
            )

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

        return self._run("decision.resolve", request, execute, mutation=True)

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
        kind: str = "human",
        scope: list[str] | None = None,
        dependencies: list[str] | None = None,
        source_revision: str = "",
        next_action: str = "inspect",
        open_gates: list[str] | None = None,
        required_input: dict[str, Any] | None = None,
        due_at: str | None = None,
    ) -> ApplicationEnvelope:
        """Create a durable Task v2."""
        request = self._mutation_context(context, operation="task.create")
        if request.authority not in {"propose", "apply"}:
            self._reject_mutation(
                "task.create",
                context,
                PermissionError("task creation requires propose authority"),
            )
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
                kind=kind,  # type: ignore[arg-type]
                scope=scope,
                dependencies=dependencies,
                source_revision=source_revision,
                next_action=next_action,
                open_gates=open_gates,
                required_input=required_input,
                due_at=due_at,
            ).model_dump(),
            mutation=True,
        )

    def task_transition(
        self,
        task_id: str,
        new_state: str,
        *,
        expected_revision: int | None = None,
        receipt_id: str | None = None,
        next_action: str | None = None,
        assignee: str | None = None,
        open_gates: list[str] | None = None,
        error_ref: str | None = None,
        required_input: dict[str, Any] | None = None,
        completion_postcondition: str | None = None,
        completion_artifact_refs: list[str] | None = None,
        values: dict[str, Any] | None = None,
        context: RequestContext | None = None,
    ) -> ApplicationEnvelope:
        """Advance a Task v2 state."""
        request = self._mutation_context(
            context,
            operation="task.transition",
            require_apply=True,
        )
        if request.authority != "apply":
            self._reject_mutation(
                "task.transition",
                context,
                PermissionError("task transition requires apply authority"),
            )
        if (
            expected_revision is None
            or isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            error = ValueError("task transition requires a positive expected_revision")
            self._emit_failure_receipt("task.transition", request, error, duration_ms=0)
            raise error
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
                assignee=assignee,
                open_gates=open_gates,
                error_ref=error_ref,
                required_input=required_input,
                completion_postcondition=completion_postcondition,
                completion_artifact_refs=completion_artifact_refs,
                idempotency_key=request.idempotency_key,
                values=values,
            ).model_dump(),
            mutation=True,
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

    @staticmethod
    def _failure_code(error: Exception) -> FailureCode:
        """Map internal exceptions to a bounded, non-content error category."""
        if isinstance(error, CompletedAfterDeadlineError):
            return "completed_after_deadline"
        if isinstance(error, DeadlineExceededError):
            return "deadline_exceeded"
        if isinstance(error, PermissionError):
            return "permission_denied"
        if isinstance(error, FileNotFoundError):
            return "not_found"
        if isinstance(error, (FileExistsError, ConflictError)):
            return "conflict"
        if isinstance(error, ResultBudgetExceededError):
            return "result_budget_exceeded"
        if isinstance(error, (ValueError, TypeError)):
            return "invalid_request"
        if isinstance(error, TimeoutError):
            return "deadline_exceeded"
        return "internal_error"

    def _emit_failure_receipt(
        self,
        operation: str,
        context: RequestContext | None,
        error: Exception,
        *,
        duration_ms: int,
        outcome: FailureOutcome | None = None,
    ) -> AuditReceipt:
        """Send bounded failure evidence to the configured audit sink."""
        principal = context.principal if context is not None else None
        failure_outcome = outcome or (
            "completed_after_deadline"
            if isinstance(error, CompletedAfterDeadlineError)
            else "completed_after_budget"
            if isinstance(error, CompletedAfterBudgetError)
            else "rejected_before_start"
            if isinstance(error, DeadlineExceededError) and "before operation started" in str(error)
            else "failed"
        )
        receipt = AuditReceipt(
            schema_version="power.receipt.v1",
            operation=operation,
            status=failure_outcome,
            request_id=context.request_id if context is not None else uuid.uuid4().hex,
            idempotency_key=context.idempotency_key if context is not None else None,
            data_sha256=_EMPTY_RESULT_SHA256,
            duration_ms=max(0, duration_ms),
            outcome=failure_outcome,
            principal_ref=principal.ref if principal is not None else None,
            principal_binding=principal.binding if principal is not None else None,
            error_code=self._failure_code(error),
            budget_ms=context.deadline_ms if context is not None else None,
            result_budget_bytes=context.max_result_bytes if context is not None else None,
        )
        if self._audit_hook is not None:
            self._notify_audit_hook(receipt)
        return receipt

    def _notify_audit_hook(self, receipt: AuditReceipt) -> None:
        """Notify the optional sink without changing the operation outcome."""
        if self._audit_hook is None:
            return
        try:
            self._audit_hook(receipt)
        except Exception as error:  # pragma: no cover - defensive sink boundary
            logger.error(
                "Application audit hook failed operation=%s exception_type=%s",
                receipt.operation,
                type(error).__name__,
            )

    def _deadline_expired(self, request: RequestContext) -> bool:
        """Check an absolute monotonic deadline without starting the action."""
        return request.deadline_at is not None and time.monotonic() >= request.deadline_at

    def _run(
        self,
        operation: str,
        context: RequestContext | None,
        action: Callable[[], Any],
        *,
        status: Literal["ok", "unavailable"] = "ok",
        mutation: bool = False,
    ) -> ApplicationEnvelope:
        if mutation and context is None:
            error = PermissionError("mutation requires an explicit RequestContext")
            self._emit_failure_receipt(operation, None, error, duration_ms=0)
            raise error
        request = context or RequestContext()
        started = time.perf_counter()
        if mutation and request.authority == "read-only":
            authority_error = PermissionError("mutation requires propose or apply authority")
            self._emit_failure_receipt(operation, context, authority_error, duration_ms=0)
            raise authority_error
        if mutation and (request.principal is None or not request.principal.is_valid()):
            principal_error = PermissionError(
                "mutation requires a valid, non-expired principal binding"
            )
            self._emit_failure_receipt(operation, context, principal_error, duration_ms=0)
            raise principal_error
        if self._deadline_expired(request):
            deadline_error = DeadlineExceededError(
                "application deadline exceeded before operation started"
            )
            self._emit_failure_receipt(
                operation,
                context,
                deadline_error,
                duration_ms=0,
                outcome="rejected_before_start",
            )
            raise deadline_error

        receipt_emitted = False
        try:
            data = action()
            elapsed_ms = (time.perf_counter() - started) * 1000
            deadline_elapsed = request.deadline_ms is not None and elapsed_ms > request.deadline_ms
            deadline_absolute = self._deadline_expired(request)
            if deadline_elapsed or deadline_absolute:
                if mutation:
                    late_error = CompletedAfterDeadlineError(
                        f"application completed after deadline ({elapsed_ms:.1f} ms)"
                    )
                    self._emit_failure_receipt(
                        operation,
                        request,
                        late_error,
                        duration_ms=int(elapsed_ms),
                        outcome="completed_after_deadline",
                    )
                    receipt_emitted = True
                    raise late_error
                deadline_error = DeadlineExceededError(
                    f"application deadline exceeded after {elapsed_ms:.1f} ms"
                )
                self._emit_failure_receipt(
                    operation,
                    request,
                    deadline_error,
                    duration_ms=int(elapsed_ms),
                    outcome="failed",
                )
                receipt_emitted = True
                raise deadline_error
            if not isinstance(data, dict):
                data = {"items": data}
            encoded = json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
            if len(encoded) > request.max_result_bytes:
                if mutation:
                    raise CompletedAfterBudgetError(
                        f"application result budget exceeded ({len(encoded)} bytes)"
                    )
                raise ResultBudgetExceededError(
                    f"application result budget exceeded ({len(encoded)} bytes)"
                )
            serializable = json.loads(encoded.decode("utf-8"))
            digest = hashlib.sha256(encoded).hexdigest()
            receipt = AuditReceipt(
                schema_version="power.receipt.v1",
                operation=operation,
                status=status,
                request_id=request.request_id,
                idempotency_key=request.idempotency_key,
                data_sha256=digest,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                principal_ref=request.principal.ref if request.principal else None,
                principal_binding=request.principal.binding if request.principal else None,
                budget_ms=request.deadline_ms,
                result_budget_bytes=request.max_result_bytes,
            )
            self._notify_audit_hook(receipt)
            actual_capability = str(
                serializable.get("actual_capability", serializable.get("actual_mode", operation))
            )
            raw_source_revision = serializable.get("source_revision")
            source_revision = str(raw_source_revision) if raw_source_revision is not None else None
            raw_degraded_reason = serializable.get("degraded_reason")
            degraded_reason = str(raw_degraded_reason) if raw_degraded_reason is not None else None
            return ApplicationEnvelope(
                operation=operation,
                status=status,
                data=serializable,
                receipt=receipt,
                actual_capability=actual_capability,
                source_revision=source_revision,
                degraded_reason=degraded_reason,
            )
        except Exception as error:
            if not receipt_emitted:
                self._emit_failure_receipt(
                    operation,
                    request,
                    error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            raise


__all__ = [
    "MAX_RESULT_BYTES",
    "ApplicationEnvelope",
    "ApplicationService",
    "AuditReceipt",
    "CompletedAfterBudgetError",
    "CompletedAfterDeadlineError",
    "DeadlineExceededError",
    "RequestContext",
    "ResultBudgetExceededError",
]
