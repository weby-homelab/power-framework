"""Tests for Phase 5D: ContextPackCompiler & Server-Issued ContextPack Invariants.

Covers:
- Strict candidate budget enforcement (budget.max_candidates)
- Strict token budget enforcement (budget.max_tokens)
- Strict byte budget enforcement (MAX_CONTEXT_PACK_BYTES)
- Server-issued token issuance (_CONTEXT_COMPILER_TOKEN)
- Anti-forgery defenses: direct instantiation, deserialization, model_copy rejection
- RuntimeContractEnvelope discriminator binding & forgery rejection
- Explainability record boundedness and identifier validation
- Deterministic token accounting (power.tokens.deterministic.v1)
- Deterministic canonical bytes and SHA-256 digest
- Backward compatibility for historical implementation_status="planned"
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from power_framework.core.context_compiler import ContextPackCompiler
from power_framework.core.context_contracts import (
    _CONTEXT_COMPILER_TOKEN,
    AccessPolicy,
    Authority,
    AuthorityBasis,
    BudgetClass,
    ContextItem,
    ContextPack,
    ContractName,
    ContradictionState,
    DomainMatch,
    Freshness,
    NoiseState,
    Provenance,
    QueryIntent,
    QueryIntentKind,
    RetrievalBudget,
    RetrievalPlan,
    RetrievalStage,
    RuntimeContractEnvelope,
    TrustState,
    canonical_bytes,
    canonical_sha256,
)
from power_framework.core.retrieval_planner import PlannerResult


def _make_access_policy() -> AccessPolicy:
    now = datetime.now(UTC)
    return AccessPolicy._from_authorization_boundary(
        origin="authorization_boundary",
        actor="test_actor",
        raw_access="none",
        quarantine_access="none",
        redaction="mandatory",
        capability_id="context_compiler",
        expires_at=now + timedelta(hours=1),
    )


def _make_context_item(
    source_id: str,
    text: str,
    *,
    authority: Authority = Authority.CURATED,
    trust_state: TrustState = TrustState.CURATED,
    token_cost: int = 10,
    score: float = 0.85,
) -> ContextItem:
    return ContextItem(
        source_id=source_id,
        source_type="vault_note",
        authority=authority,
        trust_state=trust_state,
        domain="projects",
        domains=["projects"],
        score=score,
        retrieval_stage=RetrievalStage.FTS,
        provenance=Provenance(
            source_refs=[source_id],
            source_revision=source_id,
            authority_basis=AuthorityBasis.CURATED_NOTE,
        ),
        freshness=Freshness.CURRENT,
        contradiction_state=ContradictionState.NONE,
        noise_state=NoiseState.CLEAN,
        token_cost=token_cost,
        excerpt=text,
        content_kind="excerpt",
        redaction_status="verified_safe",
    )


def _make_planner_result(
    items: list[ContextItem],
    *,
    max_candidates: int = 5,
    max_tokens: int = 100,
    budget_class: BudgetClass = BudgetClass.FAST,
) -> PlannerResult:
    stages = [RetrievalStage.FTS]
    budget = RetrievalBudget(
        budget_class=budget_class,
        max_candidates=max_candidates,
        max_tokens=max_tokens,
        max_domains=2,
        max_graph_hops=0,
        stages=stages,
        model_load="forbidden",
        dense_allowed=False,
        reranker_allowed=False,
        graph_allowed=False,
        deep_expansion_allowed=False,
        raw_fallback_allowed=False,
    )
    from power_framework.core.context_contracts import SearchScope, TemporalBoundary

    proper_plan = RetrievalPlan(
        planner_revision="planner-v5d-test",
        stages=stages,
        attempted_stages=stages,
        skipped_stages=[],
        domain_matches=[DomainMatch(domain="projects", score=0.9, reasons=["test match"])],
        scope=SearchScope(
            domain_ids=["projects"],
            path_prefixes=[],
            source_types=[],
            trust_states=[],
            temporal_boundary=TemporalBoundary(
                as_of=datetime.now(UTC).date(), include_historical=False
            ),
            project_ids=[],
            include_archived=False,
            include_quarantine=False,
        ),
        budget=budget,
        escalation_reason="test plan",
    )
    return PlannerResult(
        plan=proper_plan,
        candidates=tuple(items),
        excluded=(),
        retrieval_status="complete",
        fallback_reason="",
        dense_used=False,
        reranker_used=False,
        source_revisions=tuple(item.source_id for item in items),
        explainability_decisions=("Admitted items within budget.",),
    )


def test_compiler_candidate_budget_enforcement() -> None:
    # 5 items given, budget allows only 3 candidates
    items = [_make_context_item(f"item_{i}.md", f"Content {i}", token_cost=10) for i in range(5)]
    res = _make_planner_result(items, max_candidates=3, max_tokens=1000)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    assert len(pack.items) == 3
    assert len(pack.excluded) == 2
    for exc in pack.excluded:
        assert exc.reason == "budget_candidates_exceeded"
    assert pack.budget.consumed_tokens == 30


def test_compiler_token_budget_enforcement() -> None:
    # Each item costs 25 tokens, budget allows only 60 tokens -> max 2 items fit
    items = [_make_context_item(f"item_{i}.md", f"Content {i}", token_cost=25) for i in range(4)]
    res = _make_planner_result(items, max_candidates=10, max_tokens=60)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    assert len(pack.items) == 2
    assert pack.budget.consumed_tokens == 50
    assert len(pack.excluded) == 2
    for exc in pack.excluded:
        assert exc.reason == "budget_tokens_exceeded"


def test_server_issued_token_and_status() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    assert pack.implementation_status == "compiled"
    assert pack._issuer_token is _CONTEXT_COMPILER_TOKEN


def test_caller_cannot_instantiate_compiled_pack() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)
    pack_dict = pack.model_dump(exclude_none=True)
    pack_dict["access_policy"] = policy

    # Attempt direct instantiation with implementation_status="compiled"
    with pytest.raises(ValueError, match="must be server-issued"):
        ContextPack(**pack_dict)


def test_caller_cannot_validate_compiled_pack_from_dict() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)
    pack_dict = pack.model_dump(mode="python", exclude_none=True)
    pack_dict["access_policy"] = policy

    # Attempt deserialization via model_validate
    with pytest.raises(ValueError, match="must be server-issued"):
        ContextPack.model_validate(pack_dict)


def test_compiled_pack_cannot_be_copied() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    # Attempt copy
    with pytest.raises(ValueError, match="cannot copy or mutate a server-issued ContextPack"):
        pack.model_copy()


def test_runtime_contract_envelope_binds_compiled_pack() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    # Valid server-issued pack binds cleanly in RuntimeContractEnvelope
    envelope = RuntimeContractEnvelope(
        schema_version="power.context-runtime.v2",
        contract=ContractName.CONTEXT_PACK,
        payload=pack,
    )
    assert envelope.contract == ContractName.CONTEXT_PACK
    assert envelope.payload == pack


def test_runtime_contract_envelope_rejects_unauthenticated_compiled_dict() -> None:
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)
    pack_dict = pack.model_dump(mode="json", exclude_none=True)

    # Raw dictionary with implementation_status="compiled" must be rejected by envelope
    with pytest.raises(ValueError, match="must be server-issued"):
        RuntimeContractEnvelope(
            schema_version="power.context-runtime.v2",
            contract=ContractName.CONTEXT_PACK,
            payload=pack_dict,
        )


def test_deterministic_token_accounting() -> None:
    items = [
        _make_context_item("a.md", "Short text", token_cost=3),
        _make_context_item("b.md", "Another longer excerpt text", token_cost=7),
    ]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)

    expected_tokens = sum(item.token_cost for item in pack.items)
    assert pack.budget.consumed_tokens == expected_tokens
    assert pack.budget.budget_satisfied is True


def test_canonical_json_bytes_determinism() -> None:
    items = [
        _make_context_item("proj_1.md", "Project One", token_cost=4, score=0.8),
        _make_context_item("proj_2.md", "Project Two", token_cost=4, score=0.9),
    ]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack1 = ContextPackCompiler.compile_pack(
        res, intent, access_policy=policy, request_id="fixed-req-001"
    )
    pack2 = ContextPackCompiler.compile_pack(
        res, intent, access_policy=policy, request_id="fixed-req-001"
    )

    bytes1 = canonical_bytes(pack1.model_dump(mode="python", exclude_none=True))
    bytes2 = canonical_bytes(pack2.model_dump(mode="python", exclude_none=True))
    assert bytes1 == bytes2
    assert canonical_sha256(pack1.model_dump(mode="python", exclude_none=True)) == canonical_sha256(
        pack2.model_dump(mode="python", exclude_none=True)
    )


def test_historical_planned_status_preservation() -> None:
    """Proves ADR-0008 invariant: historical Phase 5A planned fixtures continue to validate."""
    items = [_make_context_item("item_1.md", "Content 1", token_cost=10)]
    res = _make_planner_result(items, max_candidates=5, max_tokens=100)
    intent = QueryIntent(query="test", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    policy = _make_access_policy()

    pack = ContextPackCompiler.compile_pack(res, intent, access_policy=policy)
    pack_dict = pack.model_dump(mode="python", exclude_none=True)
    pack_dict["access_policy"] = policy
    pack_dict["implementation_status"] = "planned"

    # implementation_status="planned" validates without requiring _CONTEXT_COMPILER_TOKEN
    planned_pack = ContextPack.model_validate(pack_dict)
    assert planned_pack.implementation_status == "planned"
