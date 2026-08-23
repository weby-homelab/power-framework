"""Versioned DTO models for POWER Application API v2.

These models define standard, serialization-safe, and bounded data transfer
objects used across all transport adapters (CLI, official MCP SDK, Web UI, Federation, A2A).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseDTO(BaseModel):
    """Base model enforcing strict typing and no extra unvalidated fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SourceItemDTO(BaseDTO):
    """Metadata summary of a note in the vault."""

    rel_path: str = Field(description="Normalized relative path within the vault")
    title: str = Field(description="Human-readable title or basename")
    category: str = Field(default="03_Resources", description="PARA or special category")
    size_bytes: int = Field(default=0, ge=0)
    modified_at: str = Field(default="", description="ISO 8601 UTC timestamp")
    tags: list[str] = Field(default_factory=list)
    trust_label: str = Field(
        default="local", description="Trust level: local, federated, untrusted"
    )
    sha256: str = Field(default="", description="Content hash digest")


class SourceListRequest(BaseDTO):
    """Request parameters for bounded note listing."""

    prefix: str = Field(default="", max_length=256)
    category: str | None = Field(default=None, max_length=64)
    tag: str | None = Field(default=None, max_length=64)
    cursor: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)


class SourceListResponse(BaseDTO):
    """Bounded paginated list of sources."""

    items: list[SourceItemDTO] = Field(default_factory=list)
    total_count: int = Field(default=0, ge=0)
    next_cursor: str | None = None
    source_revision: str = Field(default="", description="Vault snapshot or Git commit hash")
    actual_capability: str = "active_source_projection"
    degraded_reason: str | None = None


class SourceReadRequest(BaseDTO):
    """Request to safely read note content."""

    rel_path: str = Field(min_length=1, max_length=512)
    max_bytes: int = Field(default=2_000_000, ge=1, le=10_000_000)


class SourceReadResponse(BaseDTO):
    """Safe note reading payload with ETag and provenance."""

    rel_path: str
    content: str
    sha256: str
    etag: str
    size_bytes: int = Field(ge=0)
    modified_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    trust_label: str = "local"
    source_revision: str = ""
    actual_capability: str = "direct_file_read"
    degraded_reason: str | None = None


class SourceStatsResponse(BaseDTO):
    """Aggregated vault metrics without runtime full disk traversal."""

    vault_id: str = "default"
    total_notes: int = Field(default=0, ge=0)
    category_counts: dict[str, int] = Field(default_factory=dict)
    tag_counts: dict[str, int] = Field(default_factory=dict)
    total_links: int = Field(default=0, ge=0)
    storage_bytes: int = Field(default=0, ge=0)
    last_indexed_at: str | None = None
    healthy: bool = True
    source_revision: str = ""
    actual_capability: str = "active_source_projection"
    degraded_reason: str | None = None


class GraphNodeDTO(BaseDTO):
    """Node representation in the knowledge graph."""

    id: str = Field(description="Normalized canonical path or ID")
    label: str
    category: str = "03_Resources"
    degree: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeDTO(BaseDTO):
    """Edge representation between two notes."""

    source: str
    target: str
    relation_type: str = Field(default="wikilink")
    is_candidate: bool = Field(default=False)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphProjectionResponse(BaseDTO):
    """Precomputed bounded graph slice for visualization."""

    nodes: list[GraphNodeDTO] = Field(default_factory=list)
    edges: list[GraphEdgeDTO] = Field(default_factory=list)
    total_nodes: int = Field(default=0, ge=0)
    total_edges: int = Field(default=0, ge=0)
    max_depth: int = Field(default=2, ge=1, le=10)
    is_truncated: bool = False
    source_revision: str = ""
    actual_capability: str = "active_source_projection"
    degraded_reason: str | None = None
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)


class TaskDTO(BaseDTO):
    """Canonical PowerTask v2 domain model."""

    task_id: str = Field(min_length=1, max_length=128)
    vault_id: str = Field(default="default", max_length=64)
    tenant_id: str = Field(default="local", max_length=64)
    kind: Literal["human", "agent", "maintenance", "fleet", "federated"] = "human"
    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(default="", max_length=4096)
    owner: str = Field(default="local", max_length=64)
    assignee: str | None = Field(default=None, max_length=64)
    state: Literal[
        "backlog",
        "ready",
        "submitted",
        "working",
        "input-required",
        "auth-required",
        "blocked",
        "completed",
        "failed",
        "canceled",
        "rejected",
    ] = "backlog"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    scope: list[str] = Field(default_factory=list)
    authority: Literal["read-only", "propose", "apply"] = "read-only"
    dependencies: list[str] = Field(default_factory=list)
    source_revision: str = Field(default="", max_length=128)
    next_action: str = Field(default="inspect", max_length=512)
    open_gates: list[str] = Field(default_factory=list)
    required_input: dict[str, Any] | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    receipt_ids: list[str] = Field(default_factory=list)
    external_refs: dict[str, str] = Field(default_factory=dict)
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_at: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    execution_state: Literal[
        "none", "queued", "leased", "running", "retry-wait", "waiting-network", "dead-letter"
    ] = "none"
    error_ref: str | None = None
    dead_letter_reason: str | None = None
    revision: int = Field(default=1, ge=1)
    created_at: str = Field(default="")
    updated_at: str = Field(default="")
    due_at: str | None = None
    completion_policy: str = Field(default="standard", max_length=64)


class TaskEventDTO(BaseDTO):
    """Immutable task event record."""

    event_id: str
    task_id: str
    sequence: int = Field(ge=1)
    actor: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_digest: str
    prev_event_digest: str
    created_at: str


class DecisionDTO(BaseDTO):
    """Approval or structured input gate linked to task/proposal."""

    decision_id: str
    task_id: str
    task_revision: int = Field(ge=1)
    proposal_id: str | None = None
    proposal_sha256: str | None = None
    title: str
    description: str = ""
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    requested_by: str = "agent"
    required_authority: Literal["propose", "apply"] = "apply"
    allowed_actors: list[str] = Field(default_factory=lambda: ["*"])
    response_schema: dict[str, Literal["string", "boolean", "number"]] = Field(default_factory=dict)
    created_at: str = ""
    expires_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_action: Literal["approve", "reject", "provide_input"] | None = None
    resolution_comment: str | None = None
    resolution_input: dict[str, str | bool | int | float] | None = None
    receipt_id: str | None = None


class DecisionResolveRequest(BaseDTO):
    """Resolve a pending decision with approval or structured input."""

    decision_id: str
    action: Literal["approve", "reject", "provide_input"]
    actor: str = "human"
    authority: Literal["propose", "apply"] = "apply"
    proposal_sha256: str | None = None
    comment: str | None = None
    input_data: dict[str, Any] | None = None


class DegradedCapabilityDTO(BaseDTO):
    """Structured report of optional capability status."""

    capability: str
    status: Literal["ok", "degraded", "unavailable"]
    reason: str | None = None
    fallback: str | None = None


__all__ = [
    "BaseDTO",
    "DecisionDTO",
    "DecisionResolveRequest",
    "DegradedCapabilityDTO",
    "GraphEdgeDTO",
    "GraphNodeDTO",
    "GraphProjectionResponse",
    "SourceItemDTO",
    "SourceListRequest",
    "SourceListResponse",
    "SourceReadRequest",
    "SourceReadResponse",
    "SourceStatsResponse",
    "TaskDTO",
    "TaskEventDTO",
]
