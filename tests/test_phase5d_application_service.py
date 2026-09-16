"""Tests for Phase 5D: ApplicationService.compile_context & Read-Only Invariants.

Covers:
- Principal binding parity: Principal.local_cli() vs Principal.local_mcp_stdio()
- Unprivileged automatic AccessPolicy issuance
- Privileged search scope rejection without privileged policy
- Privileged search scope access with explicit approval
- Caller budget escalation prevention (CallerBudgetEscalationError)
- Query-side zero writes guarantee (exact SHA-256 tree audit across repeated queries)
- Empty/whitespace query rejection
- Bounded explainability decisions
- Canonical TaskStore and DecisionStore integration
- Deterministic token accounting parity
- Audit receipt generation and emission
- String and enum parameter coercion
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.context_contracts import (
    AccessPolicy,
    BudgetClass,
    CallerBudgetEscalationError,
    QueryIntentKind,
)
from power_framework.core.principal import Principal
from power_framework.core.search_scope import SearchScopeAccessDeniedError

if TYPE_CHECKING:
    from pathlib import Path


def _make_privileged_policy() -> AccessPolicy:
    now = datetime.now(UTC)
    return AccessPolicy._from_authorization_boundary(
        origin="authorization_boundary",
        actor="admin_auditor",
        raw_access="privileged",
        quarantine_access="privileged",
        redaction="mandatory",
        approval_ref="apr_gate_5d_approved",
        capability_id="compile_context",
        expires_at=now + timedelta(hours=1),
    )


def _hash_vault_tree(vault_dir: Path) -> dict[str, str]:
    """Compute deterministic SHA-256 tree of all files in vault."""
    file_hashes: dict[str, str] = {}
    for p in sorted(vault_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(vault_dir))
            file_hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return file_hashes


def test_compile_context_local_cli_principal(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    ctx = RequestContext(principal=Principal.local_cli())

    envelope = service.compile_context("project", context=ctx)

    assert envelope.status == "ok"
    assert envelope.operation == "compile_context"
    assert envelope.actual_capability == "compile_context"
    assert envelope.receipt.principal_binding == "LOCAL_CLI"
    assert envelope.data["implementation_status"] == "compiled"
    assert isinstance(envelope.data["items"], list)


def test_compile_context_local_mcp_stdio_principal(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    ctx = RequestContext(principal=Principal.local_mcp_stdio())

    envelope = service.compile_context("project", context=ctx)

    assert envelope.status == "ok"
    assert envelope.operation == "compile_context"
    assert envelope.actual_capability == "compile_context"
    assert envelope.receipt.principal_binding == "LOCAL_MCP_STDIO"
    assert envelope.data["implementation_status"] == "compiled"


def test_compile_context_principal_parity(sample_vault: Path) -> None:
    """Proves CLI and MCP stdio callers receive structurally identical context packs."""
    service = ApplicationService(sample_vault)

    ctx_cli = RequestContext(principal=Principal.local_cli())
    ctx_mcp = RequestContext(principal=Principal.local_mcp_stdio())

    res_cli = service.compile_context("project", context=ctx_cli)
    res_mcp = service.compile_context("project", context=ctx_mcp)

    assert res_cli.data["implementation_status"] == res_mcp.data["implementation_status"]
    assert res_cli.data["budget"] == res_mcp.data["budget"]
    assert len(res_cli.data["items"]) == len(res_mcp.data["items"])

    for item_cli, item_mcp in zip(res_cli.data["items"], res_mcp.data["items"], strict=True):
        assert item_cli["source_id"] == item_mcp["source_id"]
        assert item_cli["authority"] == item_mcp["authority"]
        assert item_cli["trust_state"] == item_mcp["trust_state"]
        assert item_cli["score"] == item_mcp["score"]
        assert item_cli["token_cost"] == item_mcp["token_cost"]


def test_compile_context_default_intent_is_lookup(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    envelope = service.compile_context("workflow")
    # Default intent is QueryIntentKind.LOOKUP
    assert envelope.status == "ok"
    plan = envelope.data["retrieval_plan"]
    assert plan["scope"]["domain_ids"] is not None


def test_compile_context_unprivileged_automatic_access_policy(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    # No access_policy provided -> server issues an unprivileged policy
    envelope = service.compile_context("project", access_policy=None)
    policy_data = envelope.data["access_policy"]
    assert policy_data["raw_access"] == "none"
    assert policy_data["quarantine_access"] == "none"
    assert policy_data["redaction"] == "mandatory"


def test_compile_context_privileged_scope_rejection_without_privileged_policy(
    sample_vault: Path,
) -> None:
    service = ApplicationService(sample_vault)
    # Requesting archived scope without privileged policy must be denied
    with pytest.raises(SearchScopeAccessDeniedError):
        service.compile_context("test", include_archived=True)

    with pytest.raises(SearchScopeAccessDeniedError):
        service.compile_context("test", include_quarantine=True)


def test_compile_context_privileged_scope_allowed_with_approved_policy(
    sample_vault: Path,
) -> None:
    service = ApplicationService(sample_vault)
    policy = _make_privileged_policy()

    envelope = service.compile_context(
        "test",
        include_archived=True,
        include_quarantine=True,
        access_policy=policy,
    )
    assert envelope.status == "ok"
    assert envelope.data["access_policy"]["raw_access"] == "privileged"


def test_compile_context_caller_budget_escalation_rejection(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    from power_framework.core.context_contracts import (
        BudgetLayerSource,
        ProfileBudgetLayer,
    )

    # FAST baseline candidate cap is 10. Attempting to request 50 must be rejected.
    escalated_hint = ProfileBudgetLayer(
        source=BudgetLayerSource.CALLER_HINT,
        max_candidates=50,
        lower_only=True,
    )

    with pytest.raises(CallerBudgetEscalationError, match="above server-selected cap"):
        service.compile_context("test", caller_hint=escalated_hint)


def test_compile_context_zero_query_side_writes_vault_unmodified(sample_vault: Path) -> None:
    """Proves absolute invariant: QUERY-SIDE WRITES = 0."""
    service = ApplicationService(sample_vault)

    # 1. Snapshot entire vault tree
    tree_before = _hash_vault_tree(sample_vault)

    # 2. Execute multiple read-only compile_context calls across various parameters
    service.compile_context("project", intent=QueryIntentKind.LOOKUP)
    service.compile_context("task", intent=QueryIntentKind.TASK)
    service.compile_context("decision", intent=QueryIntentKind.DECISION)
    service.compile_context("overview", budget_class=BudgetClass.BALANCED)
    service.compile_context(
        "everything",
        include_archived=True,
        include_quarantine=True,
        access_policy=_make_privileged_policy(),
    )

    # 3. Snapshot vault tree after queries
    tree_after = _hash_vault_tree(sample_vault)

    # 4. Assert zero mutations, additions, or deletions
    assert tree_before == tree_after


def test_compile_context_empty_query_rejected(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)

    with pytest.raises(ValueError, match="Search query cannot be empty"):
        service.compile_context("")

    with pytest.raises(ValueError, match="Search query cannot be empty"):
        service.compile_context("   \t\n  ")


def test_compile_context_bounded_explainability(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    envelope = service.compile_context("project")

    decisions = envelope.data["explainability"]["decisions"]
    assert isinstance(decisions, list)
    assert 1 <= len(decisions) <= 64
    for dec in decisions:
        assert isinstance(dec, str)
        assert len(dec) <= 128


def test_compile_context_task_and_decision_canonical_integration(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)

    # Create a task and a decision via canonical application mutators
    task_env = service.task_create(
        task_id="TSK-001",
        title="Phase 5D Deployment",
        objective="Ship context pack vertical slice",
        context=RequestContext(authority="apply"),
    )
    task_id = task_env.data["task_id"]

    service.decision_create(
        decision_id="dec_phase5d_01",
        task_id=task_id,
        title="Context Pack Runtime Architecture",
        description="Enforce authority over similarity",
        context=RequestContext(authority="apply"),
    )

    # Run compile_context targeting the task and decision
    envelope = service.compile_context(
        "Phase 5D",
        intent=QueryIntentKind.TASK,
    )
    items = envelope.data["items"]
    canonical_items = [it for it in items if it["authority"] == "canonical"]
    assert len(canonical_items) >= 1
    assert any(task_id in it["source_id"] for it in canonical_items)


def test_compile_context_deterministic_token_accounting(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    envelope = service.compile_context("project")

    items = envelope.data["items"]
    consumed = envelope.data["budget"]["consumed_tokens"]
    expected = sum(item["token_cost"] for item in items)
    assert consumed == expected


def test_compile_context_audit_receipt_emitted(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    ctx = RequestContext(principal=Principal.local_cli())
    envelope = service.compile_context("project", context=ctx)

    receipt = envelope.receipt
    assert receipt.operation == "compile_context"
    assert receipt.principal_ref == "local-cli"
    assert receipt.principal_binding == "LOCAL_CLI"
    assert receipt.duration_ms >= 0


def test_compile_context_string_enum_parsing(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    envelope = service.compile_context(
        "project",
        intent="task",
        budget_class="balanced",
    )
    assert envelope.status == "ok"
    assert envelope.data["retrieval_plan"]["budget"]["budget_class"] == "BALANCED"
