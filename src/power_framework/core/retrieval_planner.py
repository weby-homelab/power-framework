"""RetrievalPlanner for Phase 5D: Multi-Domain Retrieval Planning & Evidence Ordering.

Pure, deterministic, read-only orchestration of multi-domain routing, bounded
retrieval stages, intent-gated canonical admission, evidence ordering,
conflict resolution, and noise gate filtering.

Invariants:
- DOMAIN != AUTHORITY
- AUTHORITY > SEMANTIC RELEVANCE (for authority-sensitive intents)
- RETRIEVED TEXT = UNTRUSTED DATA
- ZERO MUTATIONS / ZERO QUERY-SIDE WRITES
- CALLER CAN NEVER RAISE SERVER BUDGET CAPS
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Literal

from .context_contracts import (
    Authority,
    AuthorityBasis,
    BudgetClass,
    BudgetProfile,
    ContextItem,
    ContradictionState,
    ExcludedItem,
    Freshness,
    ModelLoadPolicy,
    NoiseState,
    ProfileBudgetLayer,
    Provenance,
    QueryIntent,
    QueryIntentKind,
    RetrievalBudget,
    RetrievalBudgetPolicy,
    RetrievalPlan,
    RetrievalStage,
    SearchScope,
    TemporalBoundary,
    TrustState,
    resolve_budget_caps,
)
from .domain_policy import (
    DomainPolicyRegistry,
    RetrievalDomainRouter,
    load_domain_policy,
)
from .generation_index import resolve_active_generation
from .parser import parse_frontmatter
from .search_scope import (
    SearchScopeAccessDeniedError,
    UnsupportedSearchScopeError,
    compile_search_scope,
)
from .searcher import dense_embedding_ready, search_vault

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .context_contracts import AccessPolicy
    from .decision_service import DecisionService
    from .state_service import ProjectStateService
    from .task_service import TaskService


# Regex patterns for safety inspection
_INJECTION_PATTERN = re.compile(
    r"(?i)\b("
    r"ignore\s+(all\s+)?previous\s+(instructions|policy)|"
    r"disregard\s+(all\s+)?prior\s+instructions|"
    r"system\s*:\s*you\s+are|"
    r"system\s+override|"
    r"you\s+are\s+now\s+in\s+jailbreak\s+mode|"
    r"run\s+shell\s+command|"
    r"delete\s+all|"
    r"mark\s+this\s+canonical|"
    r"approve\s+this\s+decision|"
    r"exfiltrate\s+secret|"
    r"reveal\s+credentials|"
    r"change\s+the\s+retrieval\s+scope|"
    r"promote\s+this\s+raw\s+message"
    r")\b"
)

_SECRET_PATTERN = re.compile(
    r"(?i)("
    r"\bghp_[A-Za-z0-9]{36}\b|"
    r"\bgho_[A-Za-z0-9]{36}\b|"
    r"\bglpat-[A-Za-z0-9\-_]{20,}\b|"
    r"\bAddMax13\$|"
    r"-----BEGIN\s+(RSA|PGP|OPENSSH|EC)\s+PRIVATE\s+KEY-----|"
    r"\bpassword\s*[:=]\s*['\"]?\S+['\"]?|"
    r"\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
    r")"
)

_AUTHORITY_SPOOF_PATTERN = re.compile(
    r"(?i)\b("
    r"CANONICAL\s+TASK\s+COMPLETED|"
    r"CANONICAL\s+DECISION\s+APPROVED|"
    r"OFFICIAL\s+CANONICAL\s+TRUTH|"
    r"CANONICAL_LEDGER_PROOF"
    r")\b"
)

_AUTHORITY_RANK_INDEX: dict[Authority, int] = {
    Authority.CANONICAL: 0,
    Authority.VERIFIED: 1,
    Authority.CURATED: 2,
    Authority.PROPOSED: 3,
    Authority.UNVERIFIED: 4,
    Authority.UNKNOWN: 5,
}

_AUTHORITY_SENSITIVE_INTENTS: set[QueryIntentKind] = {
    QueryIntentKind.PROJECT_STATE,
    QueryIntentKind.DECISION,
    QueryIntentKind.TASK,
    QueryIntentKind.GOVERNANCE,
}
# NOTE (P38-WP03-R4): INFRASTRUCTURE and RESEARCH are intentionally NOT
# authority-sensitive. No binding contract requires them: the
# EvidenceOrderingPolicy contract (context_contracts.py,
# validate_ordering) mandates authority_sensitive=true exactly for
# {PROJECT_STATE, DECISION, TASK, GOVERNANCE}. Infrastructure and research
# evidence therefore stays relevance-ranked; authority is at most a
# tie-break there and never overrides semantic relevance.

# Canonical owner matrix: which owning-subsystem stores may contribute
# CANONICAL records for each intent. Bounded by production ownership, never
# by benchmark labels:
# - PROJECT_STATE -> ProjectStateService primary; Task/Decision related.
# - DECISION -> DecisionService primary; TaskService related on real binding.
# - TASK -> TaskService primary; DecisionService related on real binding.
# - GOVERNANCE -> all three owners, each eligibility-filtered (bounded).
# - Any other intent -> no automatic canonical injection; the planner must
#   not query every owner for every intent.
_CANONICAL_OWNERS_BY_INTENT: dict[QueryIntentKind, tuple[str, ...]] = {
    QueryIntentKind.PROJECT_STATE: ("project", "task", "decision"),
    QueryIntentKind.DECISION: ("decision", "task"),
    QueryIntentKind.TASK: ("task", "decision"),
    QueryIntentKind.GOVERNANCE: ("project", "decision", "task"),
}

# Primary owner per intent: admitted on strong OR weak (single-token)
# query evidence. Related owners need strong evidence; GOVERNANCE has no
# single primary, so every consulted owner is related-grade there.
_PRIMARY_OWNER_BY_INTENT: dict[QueryIntentKind, str] = {
    QueryIntentKind.PROJECT_STATE: "project",
    QueryIntentKind.DECISION: "decision",
    QueryIntentKind.TASK: "task",
}

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _eligibility_tokens(text: str) -> tuple[str, ...]:
    """Casefolded unicode word tokens, single letters dropped (noise).

    Snake_case identifiers are split on underscores so that each segment
    carries signal (``proj_alpha`` matches ``alpha``); hyphens already
    split via the word pattern.
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall((text or "").casefold()):
        out.extend(part for part in raw.split("_") if len(part) >= 2)
    return tuple(out)


def _meaningful_tokens(text: str) -> frozenset[str]:
    """Tokens long enough to carry topical signal (generic noise floor)."""
    return frozenset(t for t in _eligibility_tokens(text) if len(t) >= 3)


_PROJECT_TOPICAL_TOKENS: frozenset[str] = frozenset(
    {
        "project",
        "phase",
        "state",
        "status",
        "проєкт",
        "проект",
        "проєкту",
        "проекту",
        "фаза",
        "фази",
        "фазу",
        "стан",
        "статус",
    }
)


@dataclass(frozen=True)
class _CanonicalEligibility:
    """Query-derived admission verdict for one canonical record."""

    eligible_strong: bool
    eligible_weak: bool
    relevance: float
    matched: tuple[str, ...]


def _canonical_eligibility(query: str, object_id: str, match_text: str) -> _CanonicalEligibility:
    """Deterministic query-derived canonical eligibility (production rule).

    Tiers (generic retrieval logic; no benchmark/ID-specific branches, no
    authority constants — the score represents query relevance only):
    - ID-EXACT: the query names the object id (or vice versa) -> strong, 0.95.
    - PHRASE: the full query or a query bigram occurs in the record text ->
      strong, 0.80.
    - MULTI: >=2 distinct meaningful query tokens occur in the record ->
      strong, 0.55 + density bonus + term-proximity bonus (adjacent matched
      terms rank above scattered ones).
    - SINGLE: exactly 1 meaningful token -> weak (primary owners only), 0.40.
    - Otherwise ineligible: an unrelated canonical is not admitted at all,
      so raw evidence about another subject can never be outranked by it,
      while raw evidence about the SAME subject still sorts below the
      admitted canonical current record via the authority rank.
    """
    none = _CanonicalEligibility(False, False, 0.0, ())
    q = (query or "").casefold().strip()
    oid = (object_id or "").casefold()
    text = (match_text or "").casefold()
    if not q or not oid:
        return none
    text_tokens = _eligibility_tokens(match_text or "")
    text_set = frozenset(text_tokens)
    matched = sorted(t for t in _meaningful_tokens(query or "") if t in text_set)
    if len(oid) >= 3 and (oid in q or q == oid or (len(q) >= 4 and q in oid)):
        return _CanonicalEligibility(True, True, 0.95, tuple(matched) or (oid,))
    if len(q) >= 6 and q in text:
        return _CanonicalEligibility(True, True, 0.8, tuple(matched))
    query_tokens = _eligibility_tokens(query or "")
    if len(query_tokens) >= 2:
        for first, second in pairwise(query_tokens):
            if f"{first} {second}" in text:
                return _CanonicalEligibility(True, True, 0.8, tuple(matched))
    if len(matched) >= 2:
        positions = [i for i, t in enumerate(text_tokens) if t in set(matched)]
        span = max(positions) - min(positions) if len(positions) >= 2 else 0
        proximity = 0.0
        if span <= 20:
            proximity = 0.15 * (1.0 - math.log1p(span) / math.log1p(20))
        relevance = 0.55 + 0.05 * min(len(matched) - 2, 3) + proximity
        return _CanonicalEligibility(True, True, round(min(relevance, 0.9), 4), tuple(matched))
    if len(matched) == 1:
        return _CanonicalEligibility(False, True, 0.4, tuple(matched))
    return none


def _scoped_object_ids(query: str, object_ids: list[str]) -> set[str] | None:
    """Explicit scope: when the query names object ids, restrict to them.

    Hard restriction per owner dimension: a query that explicitly scopes to
    one object must not admit sibling objects from the same store.
    """
    q = (query or "").casefold()
    named = {oid for oid in object_ids if len(oid) >= 3 and oid.casefold() in q}
    return named or None


def _deterministic_token_cost(text: str) -> int:
    """Versioned deterministic token accounting algorithm power.tokens.deterministic.v1.

    Formula: max(1, (len(utf8_bytes) + 3) // 4) for non-empty string, 0 for empty.
    """
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def _inspect_vault_note_authority(
    vault_dir: Path,
    rel_path: str,
    snippet_content: str,
) -> tuple[Authority, TrustState, AuthorityBasis, str, Freshness, ContradictionState, NoiseState]:
    """Inspect vault note frontmatter and content to bind authority and provenance.

    Invariants (P38-WP03-R3):
    - TEXT != AUTHORITY; TAG != AUTHORITY; PATH != AUTHORITY; DOMAIN != AUTHORITY.
    - SELF-DECLARED METADATA MAY LOWER TRUST; IT NEVER RAISES AUTHORITY.
    - Ordinary vault notes from FTS/dense/raw retrieval stay UNVERIFIED with
      PROPOSED/RAW (or a more restrictive lowering state) without independent
      owning-subsystem proof (ProjectStateService/TaskService/DecisionService).
    """
    note_path = vault_dir / rel_path
    raw_text = ""
    if note_path.is_file():
        try:
            raw_text = note_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            raw_text = snippet_content
    else:
        raw_text = snippet_content

    fm = parse_frontmatter(raw_text) or {}
    tags = (
        [str(t).strip().lower() for t in fm.get("tags", [])]
        if isinstance(fm.get("tags"), list)
        else []
    )
    note_type = str(fm.get("type", "")).strip()
    status = str(fm.get("status", "")).strip().lower()

    # 1. Prompt Injection / Quarantine
    if (
        "quarantine" in tags
        or "prompt-injection" in tags
        or "noise" in tags
        or _INJECTION_PATTERN.search(raw_text)
    ):
        return (
            Authority.UNVERIFIED,
            TrustState.QUARANTINED,
            AuthorityBasis.RAW_CAPTURE,
            "noise_capture",
            Freshness.UNKNOWN,
            ContradictionState.UNKNOWN,
            NoiseState.QUARANTINED,
        )

    # 2. Self-declared frontmatter may only LOWER trust, never raise authority.
    # Any claim of CANONICAL/VERIFIED/CURATED (or CANONICAL_LEDGER /
    # VERIFIED_PROJECTION / CURATED_NOTE / canonical_* source_type) without
    # independent owning-subsystem proof is ignored and falls through to the
    # default UNVERIFIED ordinary-note binding below.
    declared_auth_str = str(fm.get("authority", "")).strip().lower()
    declared_trust_str = str(fm.get("trust_state", "")).strip().upper()
    declared_basis_str = str(fm.get("authority_basis", fm.get("basis", ""))).strip().upper()
    declared_source_type = str(fm.get("source_type", "")).strip().lower().replace("-", "_")
    _raising_auth = {"canonical", "verified", "curated"}
    _raising_trust = {"CANONICAL", "VERIFIED", "CURATED"}
    _raising_basis = {"CANONICAL_LEDGER", "VERIFIED_PROJECTION", "CURATED_NOTE"}
    _declares_raising = (
        declared_auth_str in _raising_auth
        or declared_trust_str in _raising_trust
        or declared_basis_str in _raising_basis
        or declared_source_type.startswith(("canonical_", "verified_", "curated_"))
    )
    if declared_auth_str and not _declares_raising:
        _lower_trust_map = {
            "RAW": TrustState.RAW,
            "PROPOSED": TrustState.PROPOSED,
            "QUARANTINED": TrustState.QUARANTINED,
            "ARCHIVED": TrustState.ARCHIVED,
            "SUPERSEDED": TrustState.SUPERSEDED,
            "NOISE": TrustState.NOISE,
        }
        _lower_basis_map = {
            "PROPOSAL": AuthorityBasis.PROPOSAL,
            "RAW_CAPTURE": AuthorityBasis.RAW_CAPTURE,
            "UNKNOWN": AuthorityBasis.UNKNOWN,
        }
        if declared_auth_str in {"unverified", "proposed"} or (
            declared_trust_str in _lower_trust_map
            or declared_basis_str in _lower_basis_map
            or declared_trust_str in {"", "PROPOSED", "RAW"}
        ):
            item_trust = _lower_trust_map.get(declared_trust_str, TrustState.PROPOSED)
            if item_trust is TrustState.QUARANTINED:
                return (
                    Authority.UNVERIFIED,
                    TrustState.QUARANTINED,
                    AuthorityBasis.RAW_CAPTURE,
                    "noise_capture",
                    Freshness.UNKNOWN,
                    ContradictionState.UNKNOWN,
                    NoiseState.QUARANTINED,
                )
            if item_trust is TrustState.RAW:
                return (
                    Authority.UNVERIFIED,
                    TrustState.RAW,
                    AuthorityBasis.RAW_CAPTURE,
                    "raw_capture",
                    Freshness.UNKNOWN,
                    ContradictionState.UNKNOWN,
                    NoiseState.CLEAN,
                )
            if item_trust in {TrustState.ARCHIVED, TrustState.SUPERSEDED}:
                contra = (
                    ContradictionState.SUPERSEDED
                    if item_trust is TrustState.SUPERSEDED
                    else ContradictionState.UNKNOWN
                )
                return (
                    Authority.UNVERIFIED,
                    item_trust,
                    AuthorityBasis.PROPOSAL,
                    "vault_note",
                    Freshness.UNKNOWN,
                    contra,
                    NoiseState.CLEAN,
                )

    # 3. Raw capture / chat
    if "raw-capture" in tags or "raw" in tags or "chat" in tags or note_type == "Daily Log":
        return (
            Authority.UNVERIFIED,
            TrustState.RAW,
            AuthorityBasis.RAW_CAPTURE,
            "raw_capture",
            Freshness.CURRENT,
            ContradictionState.NONE,
            NoiseState.CLEAN,
        )

    # 4. Superseded (lowering only: authority stays UNVERIFIED for safe routing).
    if "superseded" in tags:
        return (
            Authority.UNVERIFIED,
            TrustState.SUPERSEDED,
            AuthorityBasis.PROPOSAL,
            "vault_note",
            Freshness.STALE,
            ContradictionState.SUPERSEDED,
            NoiseState.CLEAN,
        )

    # 5. Stale / Historical / Archived (lowering only, preserves exclusion routing).
    if "historical" in tags or "stale" in tags or status == "archived":
        return (
            Authority.UNVERIFIED,
            TrustState.ARCHIVED,
            AuthorityBasis.PROPOSAL,
            "vault_note",
            Freshness.STALE,
            ContradictionState.UNKNOWN,
            NoiseState.CLEAN,
        )

    # 6. Distractor / Hard Negative (never raises; ordinary unverified note).
    if "hard-negative" in tags or "distractor" in tags:
        return (
            Authority.UNVERIFIED,
            TrustState.PROPOSED,
            AuthorityBasis.PROPOSAL,
            "vault_note",
            Freshness.UNKNOWN,
            ContradictionState.UNKNOWN,
            NoiseState.CLEAN,
        )

    # 7. Proposed / Unverified claim
    if "proposed" in tags or "unverified" in tags or status == "review":
        return (
            Authority.UNVERIFIED,
            TrustState.PROPOSED,
            AuthorityBasis.PROPOSAL,
            "unverified_research",
            Freshness.CURRENT,
            ContradictionState.NONE,
            NoiseState.CLEAN,
        )

    # 8. Authority-shaped tags/types NEVER raise without owning-service proof.
    # TEXT != AUTHORITY; TAG != AUTHORITY; PATH != AUTHORITY.
    # project-state/decision/task/infrastructure/contradiction/cross-domain/
    # code/research and OKF types Project/Area/Resource fall through to the
    # default UNVERIFIED ordinary-note binding below. Canonical authority
    # requires independent ProjectStateService/TaskService/DecisionService
    # proof in the PROJECT_STATE retrieval stage, never a vault-note tag.
    # 9. Default unverified note
    return (
        Authority.UNVERIFIED,
        TrustState.PROPOSED,
        AuthorityBasis.PROPOSAL,
        "vault_note",
        Freshness.UNKNOWN,
        ContradictionState.UNKNOWN,
        NoiseState.CLEAN,
    )


@dataclass(frozen=True)
class PlannerResult:
    """Read-only result produced by RetrievalPlanner."""

    plan: RetrievalPlan
    candidates: tuple[ContextItem, ...]
    excluded: tuple[ExcludedItem, ...]
    retrieval_status: Literal["complete", "partial", "degraded", "failed"]
    fallback_reason: str
    dense_used: bool
    reranker_used: bool
    source_revisions: tuple[str, ...]
    explainability_decisions: tuple[str, ...]


class RetrievalPlanner:
    """Pure, deterministic, read-only multi-domain retrieval planner for Phase 5D."""

    def __init__(
        self,
        vault_dir: Path,
        *,
        domain_policy: DomainPolicyRegistry | None = None,
        task_service: TaskService | None = None,
        decision_service: DecisionService | None = None,
        project_state_service: ProjectStateService | None = None,
        project_state_status: Literal["AVAILABLE", "UNAVAILABLE", "DEGRADED", "FAILED"]
        | None = None,
        project_state_reason: str = "",
        search_fn: Callable[..., list[Any]] | None = None,
        planner_revision: str = "retrieval_planner_v5d_2026",
    ) -> None:
        self.vault_dir = vault_dir.expanduser().resolve()
        self.planner_revision = planner_revision
        self._domain_policy = domain_policy
        self._task_service = task_service
        self._decision_service = decision_service
        self._project_state_service = project_state_service
        if project_state_status is None:
            if project_state_service is None:
                self._project_state_status: Literal[
                    "AVAILABLE", "UNAVAILABLE", "DEGRADED", "FAILED"
                ] = "UNAVAILABLE"
                self._project_state_reason = (
                    project_state_reason or "ProjectStateService unavailable"
                )
            else:
                self._project_state_status = "AVAILABLE"
                self._project_state_reason = project_state_reason
        else:
            self._project_state_status = project_state_status
            self._project_state_reason = project_state_reason
        self._search_fn = search_fn or search_vault

    def _get_domain_registry(self) -> DomainPolicyRegistry:
        if self._domain_policy is not None:
            return self._domain_policy
        return load_domain_policy(self.vault_dir)

    def plan(
        self,
        query_intent: QueryIntent,
        *,
        caller_hint: ProfileBudgetLayer | BudgetProfile | None = None,
        access_policy: AccessPolicy | None = None,
    ) -> RetrievalPlan:
        """Create a bounded, deterministic RetrievalPlan without performing I/O."""
        # 1. Budget Resolution
        budget_class = query_intent.budget_class
        policy = RetrievalBudgetPolicy.default(caller_hint=caller_hint)
        effective_profile = resolve_budget_caps(policy, budget_class)

        # Build class-compliant RetrievalBudget
        if budget_class is BudgetClass.FAST:
            budget = RetrievalBudget(
                budget_class=BudgetClass.FAST,
                max_candidates=effective_profile.max_candidates,
                max_tokens=min(effective_profile.max_tokens, query_intent.max_tokens or 4_000),
                max_domains=effective_profile.max_domains,
                max_graph_hops=0,
                stages=[RetrievalStage.FTS, RetrievalStage.PROJECT_STATE],
                model_load=ModelLoadPolicy.FORBIDDEN,
                dense_allowed=False,
                reranker_allowed=False,
                graph_allowed=False,
                deep_expansion_allowed=False,
                raw_fallback_allowed=False,
            )
        elif budget_class is BudgetClass.BALANCED:
            budget = RetrievalBudget(
                budget_class=BudgetClass.BALANCED,
                max_candidates=effective_profile.max_candidates,
                max_tokens=min(effective_profile.max_tokens, query_intent.max_tokens or 12_000),
                max_domains=effective_profile.max_domains,
                max_graph_hops=0,
                stages=[
                    RetrievalStage.FTS,
                    RetrievalStage.PROJECT_STATE,
                    RetrievalStage.SEMANTIC,
                    RetrievalStage.RERANK,
                ],
                model_load=ModelLoadPolicy.SELECTED_DOMAIN_ONLY,
                dense_allowed=True,
                reranker_allowed=True,
                graph_allowed=False,
                deep_expansion_allowed=False,
                raw_fallback_allowed=False,
            )
        else:  # DEEP
            budget = RetrievalBudget(
                budget_class=BudgetClass.DEEP,
                max_candidates=effective_profile.max_candidates,
                max_tokens=min(effective_profile.max_tokens, query_intent.max_tokens or 30_000),
                max_domains=effective_profile.max_domains,
                max_graph_hops=effective_profile.max_graph_hops,
                stages=[
                    RetrievalStage.FTS,
                    RetrievalStage.PROJECT_STATE,
                    RetrievalStage.SEMANTIC,
                    RetrievalStage.GRAPH_ASSISTED,
                    RetrievalStage.RERANK,
                    RetrievalStage.RAW_FALLBACK,
                ],
                model_load=ModelLoadPolicy.EXPLICIT_REQUEST_OR_ESCALATION,
                dense_allowed=True,
                reranker_allowed=True,
                graph_allowed=True,
                deep_expansion_allowed=True,
                raw_fallback_allowed=True,
            )

        # 2. Multi-Domain Routing
        registry = self._get_domain_registry()
        router = RetrievalDomainRouter(registry)
        domain_matches = list(
            router.route(
                query_intent.query,
                intent=query_intent.intent.value,
                routing_hints=tuple(query_intent.domain_hints or ()),
                max_domains=budget.max_domains,
            )
        )

        # 3. Fail closed on unsupported project scoping
        if query_intent.project_ids:
            raise UnsupportedSearchScopeError(
                "project_ids dimension is not supported in SQLite index schema (must fail closed)"
            )

        # 4. Privileged Access Check
        if (query_intent.include_archived or query_intent.include_quarantine) and (
            access_policy is None
            or access_policy.raw_access != "privileged"
            or access_policy.quarantine_access != "privileged"
        ):
            raise SearchScopeAccessDeniedError(
                "privileged search scope requested without a verified privileged AccessPolicy"
            )

        # 5. SearchScope Construction
        matched_domain_ids = [m.domain for m in domain_matches]
        effective_domain_ids: list[str]
        if query_intent.domain_hints:
            if matched_domain_ids:
                effective_domain_ids = [
                    d for d in query_intent.domain_hints if d in matched_domain_ids
                ]
                if not effective_domain_ids:
                    effective_domain_ids = list(query_intent.domain_hints)
            else:
                effective_domain_ids = list(query_intent.domain_hints)
        else:
            effective_domain_ids = matched_domain_ids

        tb = query_intent.temporal_boundary or TemporalBoundary(
            as_of=datetime.now(tz=UTC).date(), include_historical=False
        )

        scope = SearchScope(
            domain_ids=effective_domain_ids,
            path_prefixes=[],
            source_types=[],
            trust_states=[],
            temporal_boundary=tb,
            project_ids=list(query_intent.project_ids or []),
            include_archived=query_intent.include_archived,
            include_quarantine=query_intent.include_quarantine,
        )

        escalation_reason = (
            f"Admitted {len(domain_matches)} domain(s) under {budget_class.value} budget profile"
        )

        return RetrievalPlan(
            planner_revision=self.planner_revision,
            stages=list(budget.stages),
            attempted_stages=[],
            skipped_stages=list(budget.stages),
            domain_matches=domain_matches,
            scope=scope,
            budget=budget,
            escalation_reason=escalation_reason,
        )

    def retrieve(
        self,
        plan: RetrievalPlan,
        query_intent: QueryIntent,
        *,
        access_policy: AccessPolicy,
    ) -> PlannerResult:
        """Execute bounded retrieval stages, filter noise, and sort by authority policy."""
        attempted_stages: list[RetrievalStage] = []
        skipped_stages: list[RetrievalStage] = []
        decisions: list[str] = [plan.escalation_reason]
        retrieval_status: Literal["complete", "partial", "degraded", "failed"] = "complete"
        fallback_reason = ""
        dense_used = False
        reranker_used = False

        collected_items: list[ContextItem] = []
        excluded_items: list[ExcludedItem] = []
        source_revisions: set[str] = set()

        # Check compilation of search scope - must fail closed before any candidate read
        compile_search_scope(self.vault_dir, scope=plan.scope, access_policy=access_policy)

        # Stage 1: Intent-Gated Canonical Store Reader (PROJECT_STATE)
        # Eligible-set admission: only canonical records owned by the
        # intent's owner matrix AND passing deterministic query-derived
        # eligibility are admitted. Authority ordering applies AFTER this
        # admission, never as a global pre-sort over unrelated records.
        is_authority_sensitive = query_intent.intent in _AUTHORITY_SENSITIVE_INTENTS
        if RetrievalStage.PROJECT_STATE in plan.stages:
            attempted_stages.append(RetrievalStage.PROJECT_STATE)
            canonical_found = False
            owners = _CANONICAL_OWNERS_BY_INTENT.get(query_intent.intent, ())
            primary_owner = _PRIMARY_OWNER_BY_INTENT.get(query_intent.intent)
            query_text = query_intent.query or ""
            task_elig_by_id: dict[str, _CanonicalEligibility] = {}
            decision_elig_by_id: dict[str, _CanonicalEligibility] = {}
            task_records_by_id: dict[str, Any] = {}
            decision_records_by_id: dict[str, Any] = {}
            admitted_task_ids: set[str] = set()
            admitted_decision_ids: set[str] = set()
            if not owners:
                decisions.append(
                    "No canonical owners consulted for non-authority intent "
                    f"{query_intent.intent.value}; relevance-ranked evidence only."
                )
            # Read Task Store through the owning service when consulted.
            if owners and "task" in owners and self._task_service is not None:
                try:
                    tasks = self._task_service.list_tasks(limit=plan.budget.max_candidates)
                    scoped_task_ids = _scoped_object_ids(
                        query_text, [str(getattr(t, "task_id", "")) for t in tasks]
                    )
                    for t in tasks:
                        t_id = str(getattr(t, "task_id", ""))
                        task_records_by_id[t_id] = t
                        if scoped_task_ids is not None and t_id not in scoped_task_ids:
                            continue
                        t_obj = getattr(t, "objective", getattr(t, "description", "")) or ""
                        t_state = getattr(t.state, "value", t.state)
                        t_elig = _canonical_eligibility(
                            query_text, t_id, f"{t_id} {t.title} {t_obj} {t_state}"
                        )
                        task_elig_by_id[t_id] = t_elig
                        if not (
                            (primary_owner == "task" and t_elig.eligible_weak)
                            or t_elig.eligible_strong
                        ):
                            continue
                        canonical_found = True
                        admitted_task_ids.add(t_id)
                        item_text = (
                            f"Task: {t.title}\nID: {t.task_id}\nState: {t_state}\n"
                            f"Objective: {t_obj}"
                        )
                        cost = _deterministic_token_cost(item_text)
                        domains = (
                            ["tasks", plan.domain_matches[0].domain]
                            if plan.domain_matches
                            else ["tasks"]
                        )
                        collected_items.append(
                            ContextItem(
                                source_id=f"task:{t.task_id}",
                                source_type="canonical_task",
                                authority=Authority.CANONICAL,
                                trust_state=TrustState.CANONICAL,
                                domain=domains[0],
                                domains=domains,
                                score=t_elig.relevance,
                                retrieval_stage=RetrievalStage.PROJECT_STATE,
                                provenance=Provenance(
                                    source_refs=[f"tasks/{t.task_id}.json"],
                                    source_revision=t.task_id,
                                    authority_basis=AuthorityBasis.CANONICAL_LEDGER,
                                ),
                                freshness=Freshness.CURRENT,
                                contradiction_state=ContradictionState.NONE,
                                noise_state=NoiseState.CLEAN,
                                token_cost=cost,
                                excerpt=item_text,
                                content_kind="excerpt",
                                redaction_status="verified_safe",
                            )
                        )
                        source_revisions.add(t.task_id)
                except Exception as exc:
                    decisions.append(f"Task canonical read skipped: {type(exc).__name__}")

            # Read Decision Store through the owning service when consulted.
            if owners and "decision" in owners and self._decision_service is not None:
                try:
                    decisions_list = self._decision_service.list_decisions(
                        limit=plan.budget.max_candidates
                    )
                    scoped_decision_ids = _scoped_object_ids(
                        query_text, [str(getattr(d, "decision_id", "")) for d in decisions_list]
                    )
                    for d in decisions_list:
                        d_id = str(getattr(d, "decision_id", ""))
                        decision_records_by_id[d_id] = d
                        if scoped_decision_ids is not None and d_id not in scoped_decision_ids:
                            continue
                        d_desc = getattr(d, "description", getattr(d, "rationale", "")) or ""
                        d_status = getattr(d.status, "value", d.status)
                        d_elig = _canonical_eligibility(
                            query_text, d_id, f"{d_id} {d.title} {d_desc} {d_status}"
                        )
                        decision_elig_by_id[d_id] = d_elig
                        if not (
                            (primary_owner == "decision" and d_elig.eligible_weak)
                            or d_elig.eligible_strong
                        ):
                            continue
                        canonical_found = True
                        admitted_decision_ids.add(d_id)
                        item_text = (
                            f"Decision: {d.title}\nID: {d.decision_id}\n"
                            f"Status: {d_status}\nDescription: {d_desc}"
                        )
                        cost = _deterministic_token_cost(item_text)
                        domains = (
                            ["decisions", plan.domain_matches[0].domain]
                            if plan.domain_matches
                            else ["decisions"]
                        )
                        collected_items.append(
                            ContextItem(
                                source_id=f"decision:{d.decision_id}",
                                source_type="canonical_decision",
                                authority=Authority.CANONICAL,
                                trust_state=TrustState.CANONICAL,
                                domain=domains[0],
                                domains=domains,
                                score=d_elig.relevance,
                                retrieval_stage=RetrievalStage.PROJECT_STATE,
                                provenance=Provenance(
                                    source_refs=[f"decisions/{d.decision_id}.json"],
                                    source_revision=d.decision_id,
                                    authority_basis=AuthorityBasis.CANONICAL_LEDGER,
                                ),
                                freshness=Freshness.CURRENT,
                                contradiction_state=ContradictionState.NONE,
                                noise_state=NoiseState.CLEAN,
                                token_cost=cost,
                                excerpt=item_text,
                                content_kind="excerpt",
                                redaction_status="verified_safe",
                            )
                        )
                        source_revisions.add(d.decision_id)
                except Exception as exc:
                    decisions.append(f"Decision canonical read skipped: {type(exc).__name__}")

            # Relationship-bound related records (TASK/DECISION intents only).
            # A related record bound to an admitted primary (decision.task_id)
            # is admitted when it carries at least one matched query token of
            # its own: real relationship AND query relevance, never either
            # alone. Weak grade by construction; primaries outrank it.
            if query_intent.intent is QueryIntentKind.TASK:
                for d_id, d in decision_records_by_id.items():
                    if d_id in admitted_decision_ids:
                        continue
                    if str(getattr(d, "task_id", "")) not in admitted_task_ids:
                        continue
                    d_rel_elig = decision_elig_by_id.get(d_id)
                    if d_rel_elig is None or not d_rel_elig.matched:
                        continue
                    canonical_found = True
                    admitted_decision_ids.add(d_id)
                    d_desc = getattr(d, "description", getattr(d, "rationale", "")) or ""
                    d_status = getattr(d.status, "value", d.status)
                    item_text = (
                        f"Decision: {d.title}\nID: {d_id}\n"
                        f"Status: {d_status}\nDescription: {d_desc}"
                    )
                    cost = _deterministic_token_cost(item_text)
                    domains = (
                        ["decisions", plan.domain_matches[0].domain]
                        if plan.domain_matches
                        else ["decisions"]
                    )
                    collected_items.append(
                        ContextItem(
                            source_id=f"decision:{d_id}",
                            source_type="canonical_decision",
                            authority=Authority.CANONICAL,
                            trust_state=TrustState.CANONICAL,
                            domain=domains[0],
                            domains=domains,
                            score=0.4,
                            retrieval_stage=RetrievalStage.PROJECT_STATE,
                            provenance=Provenance(
                                source_refs=[f"decisions/{d_id}.json"],
                                source_revision=d_id,
                                authority_basis=AuthorityBasis.CANONICAL_LEDGER,
                            ),
                            freshness=Freshness.CURRENT,
                            contradiction_state=ContradictionState.NONE,
                            noise_state=NoiseState.CLEAN,
                            token_cost=cost,
                            excerpt=item_text,
                            content_kind="excerpt",
                            redaction_status="verified_safe",
                        )
                    )
                    source_revisions.add(d_id)
            elif query_intent.intent is QueryIntentKind.DECISION:
                bound_task_ids = {
                    str(getattr(decision_records_by_id[d_id], "task_id", ""))
                    for d_id in admitted_decision_ids
                    if d_id in decision_records_by_id
                }
                for t_id, t in task_records_by_id.items():
                    if t_id in admitted_task_ids or t_id not in bound_task_ids:
                        continue
                    t_rel_elig = task_elig_by_id.get(t_id)
                    if t_rel_elig is None or not t_rel_elig.matched:
                        continue
                    canonical_found = True
                    admitted_task_ids.add(t_id)
                    t_obj = getattr(t, "objective", getattr(t, "description", "")) or ""
                    t_state = getattr(t.state, "value", t.state)
                    item_text = f"Task: {t.title}\nID: {t_id}\nState: {t_state}\nObjective: {t_obj}"
                    cost = _deterministic_token_cost(item_text)
                    domains = (
                        ["tasks", plan.domain_matches[0].domain]
                        if plan.domain_matches
                        else ["tasks"]
                    )
                    collected_items.append(
                        ContextItem(
                            source_id=f"task:{t_id}",
                            source_type="canonical_task",
                            authority=Authority.CANONICAL,
                            trust_state=TrustState.CANONICAL,
                            domain=domains[0],
                            domains=domains,
                            score=0.4,
                            retrieval_stage=RetrievalStage.PROJECT_STATE,
                            provenance=Provenance(
                                source_refs=[f"tasks/{t_id}.json"],
                                source_revision=t_id,
                                authority_basis=AuthorityBasis.CANONICAL_LEDGER,
                            ),
                            freshness=Freshness.CURRENT,
                            contradiction_state=ContradictionState.NONE,
                            noise_state=NoiseState.CLEAN,
                            token_cost=cost,
                            excerpt=item_text,
                            content_kind="excerpt",
                            redaction_status="verified_safe",
                        )
                    )
                    source_revisions.add(t_id)

            # Read Project State Service via canonical owning-subsystem proof only.
            # Canonical path is .power/projects/<id>/events.jsonl, enumerated
            # via ProjectStateService.list_project_ids(); no direct ledger glob.
            if (
                owners
                and "project" in owners
                and self._project_state_service is not None
                and self._project_state_status == "AVAILABLE"
            ):
                try:
                    try:
                        project_ids = self._project_state_service.list_project_ids()
                    except Exception as exc:
                        decisions.append(f"Project state enumeration skipped: {type(exc).__name__}")
                        project_ids = []
                    scoped_project_ids = _scoped_object_ids(query_text, list(project_ids))
                    query_meaningful = _meaningful_tokens(query_text)
                    for project_id in sorted(project_ids):
                        try:
                            if (
                                scoped_project_ids is not None
                                and project_id not in scoped_project_ids
                            ):
                                continue
                            if (
                                scoped_project_ids is None
                                and query_meaningful
                                and primary_owner != "project"
                                and not (query_meaningful & _PROJECT_TOPICAL_TOKENS)
                                and not (query_meaningful & _meaningful_tokens(project_id))
                            ):
                                # Cheap identity-level pre-filter: skip ledgers
                                # whose identity shares no query signal when the
                                # query does not express project topical intent,
                                # instead of rebuilding every ledger.
                                continue
                            p_state = self._project_state_service.rebuild_project_state(project_id)
                            p_phase_raw = getattr(p_state, "current_phase", "")
                            p_phase = getattr(p_phase_raw, "value", p_phase_raw)
                            p_owner = getattr(p_state, "owner", "") or ""
                            p_members = " ".join(
                                sorted(
                                    set(getattr(p_state, "active_tasks", []) or [])
                                    | set(getattr(p_state, "ready_tasks", []) or [])
                                    | set(getattr(p_state, "blocked_tasks", []) or [])
                                    | set(getattr(p_state, "valid_decisions", []) or [])
                                )
                            )
                            p_elig = _canonical_eligibility(
                                query_text,
                                project_id,
                                f"{project_id} {p_phase} {p_owner} {p_members}",
                            )
                            if not (
                                (primary_owner == "project" and p_elig.eligible_weak)
                                or p_elig.eligible_strong
                            ):
                                continue
                            canonical_found = True
                            item_text = (
                                f"Project: {project_id}\n"
                                f"Status: {getattr(p_state, 'status', 'active')}\n"
                                f"Phase: {p_phase or 'current'}"
                            )
                            cost = _deterministic_token_cost(item_text)
                            domains = (
                                ["project-state", plan.domain_matches[0].domain]
                                if plan.domain_matches
                                else ["project-state"]
                            )
                            state_rev = str(getattr(p_state, "state_revision", "")).strip()
                            if not state_rev:
                                try:
                                    _seq, head = self._project_state_service._ledger_head(
                                        project_id
                                    )
                                    state_rev = str(head or "").strip()
                                except Exception:
                                    state_rev = ""
                            if not state_rev:
                                decisions.append(
                                    f"Project state revision unavailable for {project_id}; skipped"
                                )
                                continue
                            collected_items.append(
                                ContextItem(
                                    source_id=f"project:{project_id}",
                                    source_type="canonical_project",
                                    authority=Authority.CANONICAL,
                                    trust_state=TrustState.CANONICAL,
                                    domain=domains[0],
                                    domains=domains,
                                    score=p_elig.relevance,
                                    retrieval_stage=RetrievalStage.PROJECT_STATE,
                                    provenance=Provenance(
                                        source_refs=[f".power/projects/{project_id}/events.jsonl"],
                                        source_revision=state_rev,
                                        authority_basis=AuthorityBasis.CANONICAL_LEDGER,
                                    ),
                                    freshness=Freshness.CURRENT,
                                    contradiction_state=ContradictionState.NONE,
                                    noise_state=NoiseState.CLEAN,
                                    token_cost=cost,
                                    excerpt=item_text,
                                    content_kind="excerpt",
                                    redaction_status="verified_safe",
                                )
                            )
                            source_revisions.add(state_rev)
                        except Exception as p_err:
                            decisions.append(
                                f"Project state read skipped for {project_id}: {type(p_err).__name__}"
                            )
                except Exception as exc:
                    decisions.append(f"Project state service read skipped: {type(exc).__name__}")
            elif is_authority_sensitive and owners and "project" in owners:
                owner_reason = (
                    f"canonical owner unavailable: ProjectStateService "
                    f"{self._project_state_status}: {self._project_state_reason}"
                ).strip()
                decisions.append(owner_reason)
                retrieval_status = "degraded"
                fallback_reason = owner_reason

            if canonical_found:
                decisions.append(
                    "Retrieved canonical ledger records with Authority.CANONICAL priority."
                )

        # Stage 2: Lexical / BM25 FTS Retrieval
        if RetrievalStage.FTS in plan.stages:
            attempted_stages.append(RetrievalStage.FTS)
            try:
                fts_results = self._search_fn(
                    self.vault_dir,
                    query_intent.query,
                    max_results=plan.budget.max_candidates,
                    mode="fts",
                    scope=plan.scope,
                    access_policy=access_policy,
                )
                for r in fts_results:
                    rel_path = getattr(r, "rel_path", str(r))
                    content = getattr(r, "snippet", "") or getattr(r, "content", "")
                    score = float(getattr(r, "score", 0.5))

                    cost = _deterministic_token_cost(content)
                    raw_domain = plan.domain_matches[0].domain if plan.domain_matches else "general"
                    domains = [raw_domain]

                    # Invariant: PATH != AUTHORITY, DOMAIN != AUTHORITY
                    (
                        item_auth,
                        item_trust,
                        item_basis,
                        item_source_type,
                        freshness,
                        contradiction_state,
                        noise_state,
                    ) = _inspect_vault_note_authority(self.vault_dir, rel_path, content)

                    source_rev = (
                        hashlib.sha256(content.encode("utf-8")).hexdigest()
                        if content
                        else "unknown"
                    )

                    collected_items.append(
                        ContextItem(
                            source_id=rel_path,
                            source_type=item_source_type,
                            authority=item_auth,
                            trust_state=item_trust,
                            domain=raw_domain,
                            domains=domains,
                            score=max(0.0001, score),
                            retrieval_stage=RetrievalStage.FTS,
                            provenance=Provenance(
                                source_refs=[rel_path],
                                source_revision=source_rev,
                                authority_basis=item_basis,
                            ),
                            freshness=freshness,
                            contradiction_state=contradiction_state,
                            noise_state=noise_state,
                            token_cost=cost,
                            excerpt=content,
                            content_kind="excerpt" if content else "reference",
                            redaction_status="verified_safe",
                        )
                    )
                    source_revisions.add(source_rev)
            except Exception as exc:
                decisions.append(f"FTS search encountered exception: {type(exc).__name__}")

        # Stage 3: SEMANTIC / Dense Vector Retrieval
        if RetrievalStage.SEMANTIC in plan.stages:
            if plan.budget.dense_allowed:
                dense_ready, dense_reason = dense_embedding_ready()
                active_gen = resolve_active_generation(self.vault_dir)

                if dense_ready and active_gen is not None:
                    attempted_stages.append(RetrievalStage.SEMANTIC)
                    try:
                        dense_results = self._search_fn(
                            self.vault_dir,
                            query_intent.query,
                            max_results=plan.budget.max_candidates,
                            mode="vector",
                            scope=plan.scope,
                            access_policy=access_policy,
                        )
                        dense_used = True
                        for r in dense_results:
                            rel_path = getattr(r, "rel_path", str(r))
                            content = getattr(r, "snippet", "") or getattr(r, "content", "")
                            score = float(getattr(r, "score", 0.5))
                            cost = _deterministic_token_cost(content)
                            raw_domain = (
                                plan.domain_matches[0].domain if plan.domain_matches else "general"
                            )
                            source_rev = (
                                hashlib.sha256(content.encode("utf-8")).hexdigest()
                                if content
                                else "unknown"
                            )
                            (
                                item_auth,
                                item_trust,
                                item_basis,
                                item_source_type,
                                freshness,
                                contradiction_state,
                                noise_state,
                            ) = _inspect_vault_note_authority(self.vault_dir, rel_path, content)
                            collected_items.append(
                                ContextItem(
                                    source_id=rel_path,
                                    source_type=item_source_type,
                                    authority=item_auth,
                                    trust_state=item_trust,
                                    domain=raw_domain,
                                    domains=[raw_domain],
                                    score=max(0.0001, score),
                                    retrieval_stage=RetrievalStage.SEMANTIC,
                                    provenance=Provenance(
                                        source_refs=[rel_path],
                                        source_revision=source_rev,
                                        authority_basis=item_basis,
                                    ),
                                    freshness=freshness,
                                    contradiction_state=contradiction_state,
                                    noise_state=noise_state,
                                    token_cost=cost,
                                    excerpt=content,
                                    content_kind="excerpt" if content else "reference",
                                    redaction_status="verified_safe",
                                )
                            )
                            source_revisions.add(source_rev)
                    except Exception as exc:
                        dense_used = False
                        fallback_reason = (
                            f"dense search error ({type(exc).__name__}); fallback to FTS lexical"
                        )
                        retrieval_status = "degraded"
                        decisions.append(fallback_reason)
                else:
                    skipped_stages.append(RetrievalStage.SEMANTIC)
                    dense_used = False
                    fallback_reason = f"dense model or generation unavailable ({dense_reason}); fallback to FTS lexical"
                    retrieval_status = "degraded"
                    decisions.append(fallback_reason)
            else:
                skipped_stages.append(RetrievalStage.SEMANTIC)

        # Stage 4: GRAPH_ASSISTED Stage
        if RetrievalStage.GRAPH_ASSISTED in plan.stages:
            skipped_stages.append(RetrievalStage.GRAPH_ASSISTED)
            decisions.append(
                "Graph-assisted stage skipped: bounded graph expansion unavailable in Phase 5D."
            )

        # Stage 5: RERANK Stage
        if RetrievalStage.RERANK in plan.stages:
            skipped_stages.append(RetrievalStage.RERANK)
            reranker_used = False
            decisions.append("Rerank stage skipped: local reranker unavailable offline.")

        # Stage 6: RAW_FALLBACK Stage
        if RetrievalStage.RAW_FALLBACK in plan.stages:
            skipped_stages.append(RetrievalStage.RAW_FALLBACK)
            decisions.append("Raw fallback stage skipped: raw source fallback not invoked.")

        # Handle other planned stages to ensure exact stage partition
        for st in plan.stages:
            if st not in attempted_stages and st not in skipped_stages:
                skipped_stages.append(st)

        # -------------------------------------------------------------
        # Deduplication across domains and retrieval stages
        # -------------------------------------------------------------
        dedup_map: dict[str, ContextItem] = {}
        for item in collected_items:
            existing = dedup_map.get(item.source_id)
            if existing is None:
                dedup_map[item.source_id] = item
            else:
                # Merge domains while preserving authority-provenance-score binding
                all_domains = sorted(set(existing.domains) | set(item.domains))
                existing_rank = _AUTHORITY_RANK_INDEX[existing.authority]
                item_rank = _AUTHORITY_RANK_INDEX[item.authority]

                if existing_rank < item_rank:
                    winner = existing
                elif item_rank < existing_rank:
                    winner = item
                else:
                    winner = existing if existing.score >= item.score else item

                dedup_map[item.source_id] = ContextItem(
                    source_id=winner.source_id,
                    source_type=winner.source_type,
                    authority=winner.authority,
                    trust_state=winner.trust_state,
                    domain=winner.domain,
                    domains=all_domains,
                    score=winner.score,
                    retrieval_stage=winner.retrieval_stage,
                    provenance=winner.provenance,
                    freshness=winner.freshness,
                    contradiction_state=winner.contradiction_state,
                    noise_state=winner.noise_state,
                    token_cost=winner.token_cost,
                    excerpt=winner.excerpt,
                    content_kind=winner.content_kind,
                    redaction_status=winner.redaction_status,
                )

        deduped_items = list(dedup_map.values())
        if len(collected_items) > len(deduped_items):
            decisions.append(
                f"Deduplicated {len(collected_items) - len(deduped_items)} duplicate source reference(s)."
            )

        # -------------------------------------------------------------
        # Noise Gate & Security Inspection (Non-destructive)
        # -------------------------------------------------------------
        screened_items: list[ContextItem] = []
        for item in deduped_items:
            text = item.excerpt
            scan_text = text
            if item.source_type == "vault_note":
                note_path = self.vault_dir / item.source_id
                if note_path.is_file():
                    try:
                        scan_text = (
                            f"{text}\n{note_path.read_text(encoding='utf-8', errors='ignore')}"
                        )
                    except Exception:
                        scan_text = text

            # 1. Prompt Injection Inspection
            if _INJECTION_PATTERN.search(scan_text):
                # Quarantined: untrusted text never gains authority
                decisions.append(
                    f"Prompt injection pattern detected in {item.source_id}; quarantined."
                )
                quarantined_item = ContextItem(
                    source_id=item.source_id,
                    source_type=item.source_type,
                    authority=Authority.UNVERIFIED,
                    trust_state=TrustState.QUARANTINED,
                    domain=item.domain,
                    domains=item.domains,
                    score=item.score,
                    retrieval_stage=item.retrieval_stage,
                    provenance=Provenance(
                        source_refs=item.provenance.source_refs,
                        source_revision=item.provenance.source_revision,
                        authority_basis=AuthorityBasis.RAW_CAPTURE,
                    ),
                    freshness=item.freshness,
                    contradiction_state=item.contradiction_state,
                    noise_state=NoiseState.QUARANTINED,
                    token_cost=item.token_cost,
                    excerpt=text,
                    content_kind="excerpt",
                    redaction_status="redacted",
                )
                if access_policy.quarantine_access != "privileged":
                    excluded_items.append(
                        ExcludedItem(
                            source_id=item.source_id,
                            reason="quarantine_policy_excluded",
                        )
                    )
                    continue
                screened_items.append(quarantined_item)
                continue

            # 2. Secret Redaction Inspection
            cleaned_text = text
            redaction_status = item.redaction_status
            if _SECRET_PATTERN.search(text):
                cleaned_text = _SECRET_PATTERN.sub("[REDACTED_SECRET]", text)
                redaction_status = "redacted"
                decisions.append(f"Secret leakage detected and redacted in {item.source_id}.")

            # 3. Authority Spoof Inspection
            assigned_authority = item.authority
            assigned_trust = item.trust_state
            assigned_provenance = item.provenance
            if item.authority not in {
                Authority.CANONICAL,
                Authority.VERIFIED,
            } and _AUTHORITY_SPOOF_PATTERN.search(text):
                assigned_authority = Authority.UNVERIFIED
                assigned_trust = TrustState.RAW
                assigned_provenance = Provenance(
                    source_refs=item.provenance.source_refs,
                    source_revision=item.provenance.source_revision,
                    authority_basis=AuthorityBasis.RAW_CAPTURE,
                )
                decisions.append(
                    f"Unbacked authority claim detected in {item.source_id}; forced to RAW."
                )

            # 4. Empty / Near-Empty Noise Inspection
            assigned_noise = item.noise_state
            if not cleaned_text.strip() or len(cleaned_text.strip()) < 5:
                assigned_noise = NoiseState.DOWNRANKED

            # Check unprivileged RAW access exclusion
            if assigned_trust is TrustState.RAW and access_policy.raw_access != "privileged":
                excluded_items.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="raw_access_denied",
                    )
                )
                continue

            # Check unprivileged QUARANTINE access exclusion
            if (
                assigned_trust is TrustState.QUARANTINED
                and access_policy.quarantine_access != "privileged"
            ):
                excluded_items.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="quarantine_policy_excluded",
                    )
                )
                continue

            # Check superseded / historical exclusion if query does not request historical
            if (
                assigned_trust is TrustState.SUPERSEDED
                and not plan.scope.temporal_boundary.include_historical
            ):
                excluded_items.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="superseded_evidence_excluded",
                    )
                )
                continue

            # Check archived exclusion if query does not request archived or historical
            if (
                assigned_trust is TrustState.ARCHIVED
                and not plan.scope.include_archived
                and not plan.scope.temporal_boundary.include_historical
            ):
                excluded_items.append(
                    ExcludedItem(
                        source_id=item.source_id,
                        reason="archived_evidence_excluded",
                    )
                )
                continue

            screened_items.append(
                ContextItem(
                    source_id=item.source_id,
                    source_type=item.source_type,
                    authority=assigned_authority,
                    trust_state=assigned_trust,
                    domain=item.domain,
                    domains=item.domains,
                    score=item.score,
                    retrieval_stage=item.retrieval_stage,
                    provenance=assigned_provenance,
                    freshness=item.freshness,
                    contradiction_state=item.contradiction_state,
                    noise_state=assigned_noise,
                    token_cost=_deterministic_token_cost(cleaned_text),
                    excerpt=cleaned_text,
                    content_kind=item.content_kind,
                    redaction_status=redaction_status,
                )
            )

        # -------------------------------------------------------------
        # Evidence Ordering Policy Enforcement
        # -------------------------------------------------------------
        # Sort keys implement the approved EvidenceOrderingPolicy. For
        # authority-sensitive intents (after eligible-set admission):
        # authority -> temporal -> supersession -> contradiction ->
        # relevance -> deterministic tie-break. Raw evidence about the SAME
        # subject therefore sorts below the admitted canonical current
        # record. For non-authority intents relevance stays primary and
        # authority is only a secondary tie-break: no global authority sort
        # may erase relevance there.
        def _authority_first_key(it: ContextItem) -> tuple[int, int, int, int, float, str]:
            auth_idx = _AUTHORITY_RANK_INDEX.get(it.authority, 5)
            fresh_idx = 0 if it.freshness == Freshness.CURRENT else 1
            super_idx = 1 if it.contradiction_state == ContradictionState.SUPERSEDED else 0
            contra_idx = 0 if it.contradiction_state == ContradictionState.NONE else 1
            return (auth_idx, fresh_idx, super_idx, contra_idx, -it.score, it.source_id)

        def _relevance_first_key(it: ContextItem) -> tuple[float, int, int, int, int, str]:
            auth_idx = _AUTHORITY_RANK_INDEX.get(it.authority, 5)
            fresh_idx = 0 if it.freshness == Freshness.CURRENT else 1
            super_idx = 1 if it.contradiction_state == ContradictionState.SUPERSEDED else 0
            contra_idx = 0 if it.contradiction_state == ContradictionState.NONE else 1
            return (-it.score, auth_idx, fresh_idx, super_idx, contra_idx, it.source_id)

        if is_authority_sensitive:
            ordered_candidates = sorted(screened_items, key=_authority_first_key)
        else:
            ordered_candidates = sorted(screened_items, key=_relevance_first_key)
            decisions.append(
                "Non-authority intent: relevance-primary ordering applied; "
                "authority kept as tie-break only."
            )

        # Audit authority order violations for authority-sensitive intents
        if is_authority_sensitive:
            seen_raw = False
            for c in ordered_candidates:
                if c.authority in {Authority.UNVERIFIED, Authority.UNKNOWN}:
                    seen_raw = True
                elif seen_raw and c.authority in {Authority.CANONICAL, Authority.VERIFIED}:
                    raise RuntimeError(
                        "AUTHORITY_ORDER_VIOLATION: raw evidence outranked canonical evidence"
                    )

        # Update plan with exact execution partitions
        executed_plan = RetrievalPlan(
            planner_revision=plan.planner_revision,
            stages=list(plan.stages),
            attempted_stages=attempted_stages,
            skipped_stages=skipped_stages,
            domain_matches=list(plan.domain_matches),
            scope=plan.scope,
            budget=plan.budget,
            escalation_reason=plan.escalation_reason,
        )

        return PlannerResult(
            plan=executed_plan,
            candidates=tuple(ordered_candidates),
            excluded=tuple(excluded_items),
            retrieval_status=retrieval_status,
            fallback_reason=fallback_reason,
            dense_used=dense_used,
            reranker_used=reranker_used,
            source_revisions=tuple(sorted(source_revisions)),
            explainability_decisions=tuple(decisions),
        )

    def plan_and_retrieve(
        self,
        query_intent: QueryIntent,
        *,
        caller_hint: ProfileBudgetLayer | BudgetProfile | None = None,
        access_policy: AccessPolicy,
    ) -> PlannerResult:
        """One-step plan creation and execution."""
        plan = self.plan(query_intent, caller_hint=caller_hint, access_policy=access_policy)
        return self.retrieve(plan, query_intent, access_policy=access_policy)


__all__ = [
    "PlannerResult",
    "RetrievalPlanner",
]
