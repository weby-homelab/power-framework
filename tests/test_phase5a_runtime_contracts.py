"""Phase 5A runtime contract tests.

These tests exercise data boundaries only.  They must not invoke retrieval,
indexing, model loading, network clients, or mutation paths.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from power_framework.core.context_contracts import (
    Authority,
    BackoffPolicy,
    BitemporalEvidence,
    BudgetClass,
    BudgetProfile,
    CallerBudgetEscalationError,
    ContextBudget,
    ContextItem,
    ContextPack,
    ContractName,
    DomainMatch,
    EvidenceOrderingPolicy,
    Explainability,
    HostCapabilityProfile,
    IndexCostEstimate,
    IndexPriority,
    IndexWorkItem,
    MemoryActionDecision,
    MemoryActionKind,
    NoiseAssessment,
    NoiseDisposition,
    PayloadRetentionPolicy,
    ProfileBudgetLayer,
    QueryIntent,
    QueryIntentKind,
    ResourceProfile,
    ResourceProfileClass,
    RetentionClass,
    RetrievalBudget,
    RetrievalBudgetPolicy,
    RetrievalPlan,
    RetrievalStage,
    RuntimeContractEnvelope,
    SearchScope,
    SensitivityClass,
    TombstoneReceipt,
    TrustState,
    canonical_bytes,
    canonical_sha256,
    resolve_budget_caps,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def valid_scope() -> SearchScope:
    return SearchScope(
        domain_ids=["projects"],
        path_prefixes=["01_Projects/"],
        source_types=["markdown"],
        trust_states=[TrustState.CANONICAL],
        temporal_boundary={"as_of": date(2026, 9, 10), "include_historical": False},
        project_ids=["power38"],
        include_archived=False,
        include_quarantine=False,
    )


def valid_budget() -> RetrievalBudget:
    return RetrievalBudget(
        budget_class=BudgetClass.FAST,
        max_candidates=20,
        max_tokens=2000,
        max_domains=1,
        max_graph_hops=0,
        stages=[RetrievalStage.PROJECT_STATE, RetrievalStage.METADATA, RetrievalStage.FTS],
        model_load="forbidden",
        dense_allowed=False,
        reranker_allowed=False,
        graph_allowed=False,
        deep_expansion_allowed=False,
        raw_fallback_allowed=False,
    )


def valid_provenance() -> dict[str, object]:
    return {
        "source_refs": ["01_Projects/power38.md"],
        "source_revision": "rev-2026-09-10",
        "event_ids": ["evt-power38-1"],
        "authority_basis": "canonical_ledger",
    }


def valid_context_item() -> ContextItem:
    return ContextItem(
        source_id="source-power38-current",
        source_type="markdown",
        authority=Authority.CANONICAL,
        trust_state=TrustState.CANONICAL,
        domain="projects",
        domains=["projects"],
        score=0.9,
        retrieval_stage=RetrievalStage.FTS,
        provenance=valid_provenance(),
        freshness="current",
        contradiction_state="none",
        noise_state="clean",
        token_cost=25,
        excerpt="Synthetic project state evidence.",
        content_kind="excerpt",
        redaction_status="verified_safe",
    )


def valid_policy() -> RetrievalBudgetPolicy:
    return RetrievalBudgetPolicy(
        structural_absolute_safety_ceiling=ProfileBudgetLayer(
            source="structural_absolute_safety_ceiling",
            lower_only=False,
            max_candidates=100,
            max_tokens=10_000,
            max_domains=4,
            max_graph_hops=2,
        ),
        resource_profile_default=ProfileBudgetLayer(
            source="resource_profile_default",
            lower_only=False,
            max_candidates=80,
            max_tokens=8_000,
            max_domains=3,
            max_graph_hops=1,
        ),
        domain_policy_cap=ProfileBudgetLayer(
            source="domain_policy_cap",
            lower_only=False,
            max_candidates=60,
            max_tokens=6_000,
            max_domains=2,
            max_graph_hops=1,
        ),
        caller_hint=ProfileBudgetLayer(
            source="caller_hint",
            lower_only=True,
            max_candidates=40,
            max_tokens=4_000,
            max_domains=1,
            max_graph_hops=0,
        ),
        effective_limit_rule=(
            "min(structural_ceiling, resource_default, domain_cap, caller_hint_when_present)"
        ),
        defaults_calibration="phase5_shadow_benchmark_required",
        numeric_defaults_are_not_product_constants=True,
        profiles={
            "FAST": BudgetProfile(
                max_candidates=100,
                max_tokens=10_000,
                max_domains=4,
                max_graph_hops=2,
                model_load="forbidden",
                numeric_default_is_hypothesis=True,
            ),
            "BALANCED": BudgetProfile(
                max_candidates=100,
                max_tokens=10_000,
                max_domains=4,
                max_graph_hops=2,
                model_load="selected_domain_only",
                numeric_default_is_hypothesis=True,
            ),
            "DEEP": BudgetProfile(
                max_candidates=100,
                max_tokens=10_000,
                max_domains=4,
                max_graph_hops=2,
                model_load="explicit_request_or_escalation",
                numeric_default_is_hypothesis=True,
            ),
        },
    )


def test_valid_v1_structural_contracts_are_typed_and_frozen() -> None:
    query_intent = QueryIntent(
        query="What is the current POWER 3.8 state?",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
        include_archived=False,
        include_quarantine=False,
        max_tokens=2000,
    )
    domain_match = DomainMatch(domain="project_state", score=1.0, reasons=["explicit state query"])
    plan = RetrievalPlan(
        planner_revision="planner-v2",
        stages=[RetrievalStage.PROJECT_STATE, RetrievalStage.FTS],
        attempted_stages=[RetrievalStage.PROJECT_STATE],
        skipped_stages=[RetrievalStage.FTS],
        domain_matches=[domain_match],
        scope=valid_scope(),
        budget=valid_budget(),
        escalation_reason="",
    )
    item = valid_context_item()
    pack = ContextPack(
        request_id="request-power38-1",
        query=query_intent.query,
        intent=query_intent.intent,
        budget_class=BudgetClass.FAST,
        domains=[domain_match],
        retrieval_plan=plan,
        items=[item],
        excluded=[],
        budget=ContextBudget(
            max_tokens=2000,
            consumed_tokens=25,
            dense_used=False,
            reranker_used=False,
            index_work_triggered=False,
            budget_satisfied=True,
        ),
        explainability=Explainability(
            summary="Canonical project state selected.",
            decisions=["authority before relevance"],
            source_revisions=["rev-2026-09-10"],
        ),
        retrieval_status="complete",
        fallback_reason="",
        policy_revision="policy-v2",
        generation_revision="generation-1",
        implementation_status="planned",
        access_policy={
            "origin": "authorization_boundary",
            "actor": "server",
            "raw_access": "none",
            "quarantine_access": "none",
            "redaction": "mandatory",
            "capability_id": "cap-read-only",
            "expires_at": NOW + timedelta(hours=1),
        },
    )
    work_item = IndexWorkItem(
        source_id="source-power38-current",
        source_revision="rev-2026-09-10",
        domain_ids=["projects"],
        chunk_ids=["chunk-1"],
        priority=IndexPriority.WARM,
        reason="source changed",
        embedding_model_revision="model-rev-1",
        estimated_work=1.0,
        created_at=NOW,
        queue_state="pending",
        retry_count=0,
        idempotency_key="work-power38-1",
    )
    cost = IndexCostEstimate(
        affected_sources=1,
        affected_chunks=1,
        model_required=False,
        priority=IndexPriority.WARM,
        estimated_memory_class="low",
        estimated_cpu_class="low",
        full_rebuild=False,
        reason="one changed source",
    )

    assert query_intent.model_config["frozen"] is True
    assert pack.budget.index_work_triggered is False
    assert work_item.queue_state == "pending"
    assert cost.affected_chunks == 1
    with pytest.raises(ValidationError):
        query_intent.query = "mutation"  # type: ignore[misc]


@pytest.mark.parametrize(
    "model_factory",
    [
        lambda: QueryIntent(
            query="x",
            intent=QueryIntentKind.LOOKUP,
            budget_class=BudgetClass.FAST,
            unexpected=True,
        ),
        lambda: SearchScope.model_validate({**valid_scope().model_dump(), "unexpected": True}),
        lambda: DomainMatch(domain="x", score=0.5, reasons=["ok"], extra_field="nope"),
    ],
)
def test_unknown_fields_fail_closed(model_factory: object) -> None:
    with pytest.raises((ValidationError, TypeError)):
        model_factory()  # type: ignore[operator]


def test_closed_enums_and_wrong_discriminator_fail_closed() -> None:
    with pytest.raises(ValidationError):
        QueryIntent(query="x", intent="made_up", budget_class=BudgetClass.FAST)

    valid_query = QueryIntent(
        query="x", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST
    )
    with pytest.raises(ValidationError):
        RuntimeContractEnvelope(
            schema_version="power.context-runtime.v2",
            contract=ContractName.CONTEXT_PACK,
            payload=valid_query,
        )
    with pytest.raises(ValidationError):
        RuntimeContractEnvelope(
            schema_version="power.context-runtime.v2",
            contract="UnknownContract",
            payload=valid_query,
        )


@pytest.mark.parametrize(
    "bad_ref",
    [
        "/absolute/path",
        "C:/windows/path",
        "file:note.md",
        "http://example.invalid",
        "https://example.invalid",
        "data:text/plain,x",
        "javascript:alert(1)",
        "01_Projects/../secret.md",
        "01_Projects/%2e%2e/secret.md",
        "01_Projects/%2fsecret",
        "01_Projects\\secret.md",
        "01_Projects://secret",
        "01_Projects/\x00secret",
    ],
)
def test_source_references_reject_unsafe_forms(bad_ref: str) -> None:
    with pytest.raises(ValidationError):
        ContextItem(
            **{
                **valid_context_item().model_dump(),
                "provenance": {**valid_provenance(), "source_refs": [bad_ref]},
            }
        )


def test_identifier_is_not_a_source_reference_or_url() -> None:
    with pytest.raises(ValidationError):
        DomainMatch(domain="/etc/passwd", score=0.1, reasons=["bad"])
    with pytest.raises(ValidationError):
        DomainMatch(domain="https://example.invalid", score=0.1, reasons=["bad"])


def test_trust_authority_and_domain_axes_remain_independent() -> None:
    raw = valid_context_item().model_dump()
    raw.update({"trust_state": TrustState.RAW, "authority": Authority.CANONICAL})
    with pytest.raises(ValidationError):
        ContextItem.model_validate(raw)

    domain_only = DomainMatch(domain="canonical", score=1.0, reasons=["domain signal"])
    assert domain_only.domain == "canonical"
    domain_marked_raw = ContextItem(
        **{
            **valid_context_item().model_dump(),
            "domain": "canonical",
            "domains": ["canonical"],
            "authority": Authority.PROPOSED,
            "trust_state": TrustState.RAW,
            "provenance": {
                **valid_provenance(),
                "authority_basis": "raw_capture",
            },
        }
    )
    assert domain_marked_raw.authority is Authority.PROPOSED
    assert domain_marked_raw.trust_state is TrustState.RAW


def test_noise_quarantine_preserves_source_and_never_deletes() -> None:
    assessment = NoiseAssessment(
        action=NoiseDisposition.QUARANTINE,
        layers=["unsafe_quarantine"],
        reasons=["prompt injection text is inert data"],
        confidence=1.0,
        source_preserved=True,
        trust_state=TrustState.QUARANTINED,
    )
    assert assessment.source_preserved is True
    with pytest.raises(ValidationError):
        NoiseAssessment(
            action=NoiseDisposition.QUARANTINE,
            layers=["unsafe_quarantine"],
            reasons=["invalid"],
            confidence=1.0,
            source_preserved=True,
            trust_state=TrustState.RAW,
        )

    with pytest.raises(ValidationError):
        PayloadRetentionPolicy(
            retention_class=RetentionClass.WORKING,
            sensitivity_class=SensitivityClass.INTERNAL,
            payload_action="DELETE_AFTER_ELIGIBILITY",
            audit_metadata_retained=True,
            policy_revision="policy-1",
            noise_disposition=NoiseDisposition.QUARANTINE,
            source_delete_requires_explicit_policy=True,
        )


def test_memory_action_is_policy_engine_issued_not_caller_authority() -> None:
    data = {
        "action": MemoryActionKind.REQUEST_APPROVAL,
        "signal": "manual review required",
        "domain": "governance",
        "trust_state": TrustState.PROPOSED,
        "confidence": 0.5,
        "reason": "synthetic contract test",
        "origin": "policy_engine",
        "policy_revision": "policy-1",
        "server_derived": True,
    }
    with pytest.raises(ValidationError):
        MemoryActionDecision.model_validate(data)
    action = MemoryActionDecision.from_policy_engine(**data)
    assert action.server_derived is True
    assert action.origin == "policy_engine"

    with pytest.raises(ValidationError):
        RuntimeContractEnvelope(
            schema_version="power.context-runtime.v2",
            contract=ContractName.MEMORY_ACTION,
            payload=data,
        )


def test_bitemporal_timestamps_are_aware_and_intervals_are_ordered() -> None:
    evidence = BitemporalEvidence(
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
    )
    assert evidence.observed_at.tzinfo is not None
    with pytest.raises(ValidationError):
        BitemporalEvidence(observed_at=datetime(2026, 1, 1), recorded_at=NOW)
    with pytest.raises(ValidationError):
        BitemporalEvidence(
            observed_at=NOW,
            recorded_at=NOW,
            valid_from=NOW,
            valid_to=NOW - timedelta(seconds=1),
        )


def test_tombstone_receipt_requires_explicit_delete_semantics() -> None:
    common = {
        "receipt_id": "receipt-1",
        "source_ref": "source-1",
        "source_revision": "a" * 64,
        "payload_digest": "b" * 64,
        "metadata_digest": "c" * 64,
        "observed_at": NOW,
        "recorded_at": NOW,
        "policy_revision": "policy-1",
        "authorization_ref": "auth-1",
        "sensitivity_class": SensitivityClass.INTERNAL,
        "redaction_policy_revision": "redact-1",
        "payload_eligibility_proof": "eligibility-1",
        "audit_metadata_retained": True,
        "noise_never_deletes_source": True,
        "reason": "approved retention policy",
        "reason_is_secret_free": True,
    }
    receipt = TombstoneReceipt(**common, receipt_kind="DELETION", payload_action="DELETED")
    assert receipt.payload_action == "DELETED"
    with pytest.raises(ValidationError):
        TombstoneReceipt(**common, receipt_kind="DELETION", payload_action="EXPIRED")


def test_evidence_ordering_is_stagewise_and_authority_sensitive() -> None:
    policy = EvidenceOrderingPolicy(
        intent_class="project_state",
        ordered_stages=[
            "access_policy",
            "authority_policy",
            "temporal_validity",
            "supersession",
            "contradiction_state",
            "semantic_relevance",
            "reranking",
            "diversity_token_packing",
        ],
        authority_sensitive=True,
        authority_rank=["canonical", "verified", "curated", "proposed", "raw", "unknown"],
        semantic_relevance_may_override_authority=False,
        supersession_precedes_relevance=True,
        score_model="separate-explainable-stages",
    )
    assert policy.ordered_stages[0] == "access_policy"
    invalid_policy = policy.model_dump()
    invalid_policy["semantic_relevance_may_override_authority"] = True
    with pytest.raises(ValidationError):
        EvidenceOrderingPolicy.model_validate(invalid_policy)


def test_resource_and_host_profiles_are_abstract_not_host_names() -> None:
    resource = ResourceProfile(
        profile_class=ResourceProfileClass.STANDARD,
        calibration_status="phase5_shadow_benchmark_required",
        numeric_defaults_are_hypotheses=True,
        host_specific_facts_are_not_framework_invariants=True,
        default_max_workers=2,
        default_memory_class="STANDARD",
        default_model_policy="OPTIONAL_LOCAL",
    )
    host = HostCapabilityProfile(
        profile_id="host-profile-1",
        resource_profile=resource.profile_class,
        deployment_profile_ref="deployment-profile-1",
        cpu_class="generic",
        memory_class="standard",
        model_capabilities=["local-onnx"],
        framework_invariants_excluded=True,
    )
    assert host.resource_profile == ResourceProfileClass.STANDARD
    with pytest.raises(ValidationError):
        HostCapabilityProfile.model_validate({**host.model_dump(), "host_name": "WS"})


def test_retry_policy_is_bounded_and_does_not_create_a_worker() -> None:
    retry = __import__(
        "power_framework.core.context_contracts", fromlist=["RetryPolicy"]
    ).RetryPolicy(
        max_automatic_retries=2,
        max_total_requeues=4,
        max_manual_requeues=1,
        backoff=BackoffPolicy(
            strategy="bounded_exponential",
            initial_delay_ms=100,
            multiplier=2.0,
            max_delay_ms=1000,
            jitter=True,
        ),
        dead_letter_after_exhaustion=True,
        explicit_review_before_requeue=True,
        requeue_requires_revision_check=True,
        no_unbounded_retries=True,
        secret_free_error_receipt=True,
    )
    assert retry.max_total_requeues == 4
    with pytest.raises(ValidationError):
        BackoffPolicy(
            strategy="exponential",
            initial_delay_ms=1001,
            multiplier=2.0,
            max_delay_ms=1000,
            jitter=False,
        )


def test_caller_can_only_lower_server_budget_caps() -> None:
    effective = resolve_budget_caps(valid_policy(), BudgetClass.FAST)
    assert effective.max_candidates == 40
    assert effective.max_tokens == 4000
    assert effective.max_domains == 1
    assert effective.max_graph_hops == 0

    elevated = valid_policy().model_copy(
        update={
            "caller_hint": ProfileBudgetLayer(
                source="caller_hint",
                lower_only=True,
                max_candidates=61,
            )
        }
    )
    with pytest.raises(CallerBudgetEscalationError):
        resolve_budget_caps(elevated, BudgetClass.FAST)


def test_canonical_serialization_is_utc_compact_and_finite() -> None:
    first = BitemporalEvidence(
        observed_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 10, 14, tzinfo=timezone(timedelta(hours=2))),
    )
    second = BitemporalEvidence(
        observed_at=datetime(2026, 9, 10, 7, tzinfo=timezone(timedelta(hours=-5))),
        recorded_at=datetime(2026, 9, 10, 14, tzinfo=timezone(timedelta(hours=2))),
    )
    assert first.to_canonical_bytes() == second.to_canonical_bytes()
    assert first.digest() == canonical_sha256(json.loads(first.to_canonical_bytes()))
    assert b"+00:00" not in first.to_canonical_bytes()
    with pytest.raises(ValueError, match="NaN"):
        canonical_bytes({"value": math.nan})
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})


def test_contract_construction_has_no_filesystem_or_model_side_effects(tmp_path: Path) -> None:
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    QueryIntent(query="read only", intent=QueryIntentKind.LOOKUP, budget_class=BudgetClass.FAST)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after == []


def test_contract_import_does_not_load_neural_or_network_runtime() -> None:
    code = (
        "import sys; import power_framework.core.context_contracts; "
        "assert 'onnxruntime' not in sys.modules; "
        "assert 'tokenizers' not in sys.modules; "
        "assert 'numpy' not in sys.modules"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    completed = subprocess.run(  # noqa: S603 -- interpreter and code are constants.
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
