"""PowerClient port connecting the Web UI to POWER ApplicationService."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from power_framework.core.application import ApplicationEnvelope, ApplicationService, RequestContext
from power_framework.core.application_models import (
    GraphProjectionResponse,
    SourceListRequest,
    SourceListResponse,
    SourceReadResponse,
    SourceStatsResponse,
    TaskDTO,
    TaskEventDTO,
)


class PowerClient:
    """Client port interacting with POWER core exclusively through ApplicationService boundary."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self._service = ApplicationService(self.vault_path)

    def discover(self, actor: str = "web") -> ApplicationEnvelope:
        """Fetch system capability manifest."""
        ctx = RequestContext(actor=actor, authority="read-only")
        return self._service.discover(context=ctx)

    def get_source_stats(self, actor: str = "web") -> SourceStatsResponse:
        """Fetch aggregated vault statistics."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.source_stats(context=ctx)
        return SourceStatsResponse.model_validate(env.data)

    def list_sources(
        self,
        *,
        prefix: str = "",
        category: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        actor: str = "web",
    ) -> SourceListResponse:
        """List notes in vault."""
        req = SourceListRequest(
            prefix=prefix, category=category, tag=tag, limit=limit, cursor=cursor
        )
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.source_list(req, context=ctx)
        return SourceListResponse.model_validate(env.data)

    def read_source(
        self, rel_path: str, max_bytes: int = 2_000_000, actor: str = "web"
    ) -> SourceReadResponse:
        """Read a note securely."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.source_read(rel_path, max_bytes=max_bytes, context=ctx)
        return SourceReadResponse.model_validate(env.data)

    def get_graph_projection(
        self,
        max_nodes: int = 500,
        focus_path: str | None = None,
        max_depth: int = 2,
        actor: str = "web",
    ) -> GraphProjectionResponse:
        """Fetch knowledge graph projection."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.source_graph(
            max_nodes=max_nodes,
            focus_path=focus_path,
            max_depth=max_depth,
            context=ctx,
        )
        return GraphProjectionResponse.model_validate(env.data)

    def search(
        self,
        query: str,
        *,
        mode: str = "auto",
        max_results: int = 20,
        actor: str = "web",
    ) -> ApplicationEnvelope:
        """Search the vault."""
        ctx = RequestContext(actor=actor, authority="read-only")
        return self._service.retrieve(query, mode=mode, max_results=max_results, context=ctx)

    def list_tasks(
        self,
        *,
        state: str | None = None,
        owner: str | None = None,
        assignee: str | None = None,
        limit: int = 100,
        offset: int = 0,
        actor: str = "web",
    ) -> list[TaskDTO]:
        """List Task v2 items."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.task_list(
            state=state, owner=owner, assignee=assignee, limit=limit, offset=offset, context=ctx
        )
        raw_items = env.data.get("items", []) if isinstance(env.data, dict) else env.data
        if isinstance(raw_items, list):
            return [TaskDTO.model_validate(item) for item in raw_items]
        return []

    def get_task(self, task_id: str, actor: str = "web") -> TaskDTO:
        """Read a single Task v2."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.task_read(task_id, context=ctx)
        return TaskDTO.model_validate(env.data)

    def create_task(
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
        actor: str = "web",
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> TaskDTO:
        """Create a new Task v2."""
        ctx = RequestContext(actor=actor, authority="propose", idempotency_key=idempotency_key)
        env = self._service.task_create(
            task_id=task_id,
            title=title,
            objective=objective,
            owner=owner,
            assignee=assignee,
            state=state,
            priority=priority,
            authority=authority,
            context=ctx,
            **kwargs,
        )
        return TaskDTO.model_validate(env.data)

    def transition_task(
        self,
        task_id: str,
        new_state: str,
        *,
        actor: str = "web",
        expected_revision: int | None = None,
        receipt_id: str | None = None,
        next_action: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> TaskDTO:
        """Transition Task v2 state."""
        ctx = RequestContext(actor=actor, authority="apply", idempotency_key=idempotency_key)
        env = self._service.task_transition(
            task_id=task_id,
            new_state=new_state,
            expected_revision=expected_revision,
            receipt_id=receipt_id,
            next_action=next_action,
            context=ctx,
            **kwargs,
        )
        return TaskDTO.model_validate(env.data)

    def get_task_events(
        self, task_id: str, since_sequence: int = 0, actor: str = "web"
    ) -> list[TaskEventDTO]:
        """Fetch task event stream."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.task_events(task_id, since_sequence=since_sequence, context=ctx)
        raw_items = env.data.get("items", []) if isinstance(env.data, dict) else env.data
        if isinstance(raw_items, list):
            return [TaskEventDTO.model_validate(item) for item in raw_items]
        return []

    def propose(
        self,
        rel_path: str,
        content: str,
        actor: str = "web",
        idempotency_key: str | None = None,
    ) -> ApplicationEnvelope:
        """Create a proposal for a note modification."""
        ctx = RequestContext(actor=actor, authority="propose", idempotency_key=idempotency_key)
        return self._service.propose(rel_path, content, context=ctx)

    def apply(
        self,
        proposal_id: str,
        approved: bool = True,
        actor: str = "web",
        idempotency_key: str | None = None,
    ) -> ApplicationEnvelope:
        """Apply a durable proposal by content-addressed ID only."""
        ctx = RequestContext(actor=actor, authority="apply", idempotency_key=idempotency_key)
        if not proposal_id.strip():
            raise ValueError("proposal_id is required")
        return self._service.apply_proposal(proposal_id, approved=approved, context=ctx)

    def list_decisions(self, actor: str = "web") -> list[dict[str, Any]]:
        """Read canonical DecisionService projections."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.decision_list(context=ctx)
        raw = env.data.get("items", []) if isinstance(env.data, dict) else env.data
        return raw if isinstance(raw, list) else []

    def resolve_decision(
        self,
        decision_id: str,
        *,
        action: str,
        input_data: dict[str, Any] | None = None,
        comment: str | None = None,
        actor: str = "web",
        idempotency_key: str | None = None,
    ) -> ApplicationEnvelope:
        """Resolve a canonical decision through ApplicationService."""
        ctx = RequestContext(actor=actor, authority="apply", idempotency_key=idempotency_key)
        return self._service.decision_resolve(
            decision_id,
            action=action,
            input_data=input_data,
            comment=comment,
            context=ctx,
        )

    def get_receipts(self, limit: int = 100, actor: str = "web") -> list[dict[str, Any]]:
        """Fetch audit receipts."""
        ctx = RequestContext(actor=actor, authority="read-only")
        env = self._service.receipt(limit=limit, context=ctx)
        receipts = env.data.get("receipts", [])
        if isinstance(receipts, list):
            return receipts
        return []


__all__ = ["PowerClient"]
