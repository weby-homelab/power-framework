"""ContextPackCompiler for Phase 5D: Multi-Domain ContextPack Compilation.

Compiles PlannerResult into an authoritative, server-issued ContextPack while
strictly enforcing:
- Candidate count <= budget.max_candidates
- Consumed tokens <= budget.max_tokens
- Total excerpt bytes <= MAX_CONTEXT_PACK_BYTES (2,000,000 bytes)
- Server-issued issuance token (_CONTEXT_COMPILER_TOKEN)
- Zero mutation of caller data or state
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import TYPE_CHECKING, Literal

from .context_contracts import (
    MAX_CONTEXT_PACK_BYTES,
    AccessPolicy,
    ContextBudget,
    ContextItem,
    ContextPack,
    ExcludedItem,
    Explainability,
    QueryIntent,
)

if TYPE_CHECKING:
    from .retrieval_planner import PlannerResult

_IDENTIFIER_SAFE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _safe_identifier(val: str, prefix: str = "id") -> str:
    """Ensure a string conforms to the Identifier contract pattern without illegal segments."""
    if not val:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"
    cleaned = val.lstrip("/\\")
    if "://" in cleaned:
        cleaned = cleaned.split("://")[-1]
    if len(cleaned) > 1 and cleaned[1] == ":":
        cleaned = cleaned[2:].lstrip("/\\")
    parts = [p for p in cleaned.split("/") if p and p != ".."]
    cleaned = "/".join(parts)
    cleaned = re.sub(r"[^A-Za-z0-9._:/-]", "_", cleaned)
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"{prefix}-{cleaned}"
    cleaned = cleaned[:256]
    if _IDENTIFIER_SAFE_RE.fullmatch(cleaned):
        return cleaned
    return f"{prefix}-{hashlib.sha256(val.encode('utf-8')).hexdigest()[:16]}"


class ContextPackCompiler:
    """Authoritative, server-side ContextPack compiler for Phase 5D."""

    def __init__(
        self,
        *,
        compiler_revision: str = "context_compiler_v5d_2026",
    ) -> None:
        self.compiler_revision = compiler_revision

    def compile(
        self,
        planner_result: PlannerResult,
        query_intent: QueryIntent,
        *,
        access_policy: AccessPolicy,
        request_id: str | None = None,
        policy_revision: str | None = None,
        generation_revision: str | None = None,
    ) -> ContextPack:
        """Compile a PlannerResult into a server-issued, budget-bounded ContextPack."""
        plan = planner_result.plan
        budget = plan.budget
        max_candidates = budget.max_candidates
        max_tokens = budget.max_tokens

        packed_items: list[ContextItem] = []
        new_excluded: list[ExcludedItem] = []
        accumulated_tokens = 0
        accumulated_bytes = 0

        # Enforce candidate, token, and byte budgets in candidate order
        for item in planner_result.candidates:
            item_bytes = len(item.excerpt.encode("utf-8"))

            if len(packed_items) >= max_candidates:
                new_excluded.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="budget_candidates_exceeded",
                    )
                )
                continue

            if accumulated_tokens + item.token_cost > max_tokens:
                new_excluded.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="budget_tokens_exceeded",
                    )
                )
                continue

            if accumulated_bytes + item_bytes > MAX_CONTEXT_PACK_BYTES:
                new_excluded.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="byte_limit_exceeded",
                    )
                )
                continue

            packed_items.append(item)
            accumulated_tokens += item.token_cost
            accumulated_bytes += item_bytes

        all_excluded = tuple(list(planner_result.excluded) + new_excluded)

        context_budget = ContextBudget(
            max_tokens=max_tokens,
            consumed_tokens=accumulated_tokens,
            dense_used=planner_result.dense_used,
            reranker_used=planner_result.reranker_used,
            index_work_triggered=False,
            budget_satisfied=True,
        )

        safe_req_id = _safe_identifier(request_id or f"req-{uuid.uuid4().hex[:16]}", prefix="req")
        safe_policy_rev = _safe_identifier(policy_revision or plan.planner_revision, prefix="pol")
        safe_gen_rev = _safe_identifier(generation_revision or "gen-v5d-active", prefix="gen")

        decisions_list = [d[:2048] for d in planner_result.explainability_decisions][:64]
        if not decisions_list:
            decisions_list = ["Retrieval and context compilation complete."]

        raw_revs = list(planner_result.source_revisions) or [
            item.source_id for item in packed_items
        ]
        safe_revs = list(dict.fromkeys(_safe_identifier(r, prefix="src") for r in raw_revs))[:128]
        if not safe_revs:
            safe_revs = [safe_gen_rev]

        domain_count = len(plan.domain_matches)
        item_count = len(packed_items)
        summary = f"Compiled {item_count} item(s) ({accumulated_tokens} tokens) across {domain_count} domain(s)"[
            :2048
        ]

        explainability = Explainability(
            summary=summary,
            decisions=decisions_list,
            source_revisions=safe_revs,
        )

        status: Literal["complete", "partial", "degraded", "failed"] = (
            planner_result.retrieval_status
        )
        fallback_reason = planner_result.fallback_reason
        if status in {"degraded", "failed"} and not fallback_reason:
            fallback_reason = "Retrieval completed with degraded status"
        elif status not in {"degraded", "failed"} and not fallback_reason:
            fallback_reason = ""

        return ContextPack._from_compiler(
            request_id=safe_req_id,
            query=query_intent.query,
            intent=query_intent.intent,
            budget_class=query_intent.budget_class,
            domains=plan.domain_matches,
            retrieval_plan=plan,
            items=tuple(packed_items),
            excluded=all_excluded,
            budget=context_budget,
            explainability=explainability,
            retrieval_status=status,
            fallback_reason=fallback_reason,
            policy_revision=safe_policy_rev,
            generation_revision=safe_gen_rev,
            access_policy=access_policy,
        )

    @classmethod
    def compile_pack(
        cls,
        planner_result: PlannerResult,
        query_intent: QueryIntent,
        *,
        access_policy: AccessPolicy,
        request_id: str | None = None,
        policy_revision: str | None = None,
        generation_revision: str | None = None,
    ) -> ContextPack:
        """Classmethod convenience to compile a ContextPack with default compiler."""
        return cls().compile(
            planner_result,
            query_intent,
            access_policy=access_policy,
            request_id=request_id,
            policy_revision=policy_revision,
            generation_revision=generation_revision,
        )


__all__ = [
    "ContextPackCompiler",
]
