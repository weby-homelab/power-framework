#!/usr/bin/env python3
"""POWER 3.8 Phase 5E — Shadow Benchmark / Legacy Comparison Runner.

Executes read-only shadow comparison:
  LEGACY RETRIEVAL (ApplicationService.retrieve)
  vs
  SHADOW RETRIEVAL (ApplicationService.compile_context)
on the frozen evaluation corpus v1.1.

Evaluates:
  - Recall@1, Recall@3, Recall@5, Recall@10
  - MRR (Mean Reciprocal Rank)
  - MAP (Mean Average Precision)
  - nDCG@5, nDCG@10
  - Context Precision
  - Authority-order violations
  - Expected-exclusion leaks
  - Latency (p50, p90, p95, mean)
  - Token and byte accounting
  - Dense and reranker usage tracking
  - Hard Invariants:
      * authority_order_violations == 0 (Shadow)
      * query_side_writes == 0 (SHA-256 tree audit)
      * scope_escape == 0
      * secret_leakage == 0
      * prompt_injection_authority_escalation == 0
      * determinism_mismatches == 0
      * default_switches == 0
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import platform
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from power_framework.core.application import ApplicationService, RequestContext  # noqa: E402
from power_framework.core.principal import Principal  # noqa: E402


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _hash_vault_tree(vault_dir: Path) -> dict[str, str]:
    """Compute deterministic SHA-256 tree of all files in vault."""
    file_hashes: dict[str, str] = {}
    for p in sorted(vault_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(vault_dir))
            file_hashes[rel] = _sha256_file(p)
    return file_hashes


def normalize_source_id(raw_id: str) -> str:
    """Extract canonical source ID matching corpus note stem."""
    cleaned = raw_id.removeprefix("task:").removeprefix("decision:").removeprefix("project:")
    return Path(cleaned).stem


# P38-WP03-R1 frozen fixture projection (query-independent, ground-truth-independent).
# Maps synthetic corpus stems to existing production runtime owners where the
# architecture supports canonical ledger provenance. No benchmark-only authority
# promotion: this map never assigns authority, it only declares the expected
# owner so the harness can verify real runtime provenance (CANONICAL_LEDGER etc).
# Frozen before evaluation; must not be tuned per query or per ground truth.
FROZEN_FIXTURE_OWNER_MAP: dict[str, str] = {
    "p38-src-project-current": "ProjectStateService",
    "p38-src-project-current-ua": "ProjectStateService",
    "p38-src-project-raw-chat": "VaultNote",
    "p38-src-project-superseded": "ProjectStateService",
    "p38-src-decision-current": "DecisionService",
    "p38-src-decision-raw": "VaultNote",
    "p38-src-decision-old": "DecisionService",
    "p38-src-task-current": "TaskService",
    "p38-src-task-raw": "VaultNote",
    "p38-src-code-en": "VaultNote",
    "p38-src-code-ua": "VaultNote",
    "p38-src-infra-current": "VaultNote",
    "p38-src-infra-stale": "VaultNote",
    "p38-src-research-curated": "VaultNote",
    "p38-src-research-unverified": "VaultNote",
    "p38-src-contradiction-canonical": "ProjectStateService",
    "p38-src-contradiction-raw": "VaultNote",
    "p38-src-noise-injection": "Quarantine",
    "p38-src-hard-negative": "VaultNote",
    "p38-src-cross-domain": "VaultNote",
}

# Ground-truth-aware authority ranking (lower is stronger).
FROZEN_AUTHORITY_RANK: dict[str, int] = {
    "canonical": 0,
    "verified": 1,
    "curated": 2,
    "proposed": 3,
    "unverified": 4,
    "unknown": 5,
}

# Runtime bases that can honestly support canonical/verified/curated authority.
# Must come from real runtime provenance, never from benchmark labels.
CANONICAL_RUNTIME_BASES = frozenset({"CANONICAL_LEDGER", "VERIFIED_PROJECTION", "CURATED_NOTE"})


def project_fixture_to_runtime_owner(source_id_stem: str) -> str:
    """Frozen deterministic projection of a synthetic fixture to its runtime owner.

    Query-independent and ground-truth-independent: uses only the stem.
    Returns "Unknown" when the fixture has no declared owner.
    """
    return FROZEN_FIXTURE_OWNER_MAP.get(source_id_stem, "Unknown")


def has_canonical_runtime_provenance(*, authority: str, basis: str, source_type: str) -> bool:
    """Check that a retrieved item really carries canonical runtime provenance.

    UNVERIFIED != CANONICAL. A benchmark label alone is not provenance: the
    runtime authority must be canonical/verified/curated with a compatible
    canonical basis (CANONICAL_LEDGER / VERIFIED_PROJECTION / CURATED_NOTE)
    and a canonical source_type. No benchmark-only promotion allowed.
    """
    auth = (authority or "unknown").lower()
    if auth not in {"canonical", "verified", "curated"}:
        return False
    b = (basis or "UNKNOWN").upper()
    if b not in CANONICAL_RUNTIME_BASES:
        return False
    st = (source_type or "").lower()
    return st.startswith(("canonical_", "verified_", "curated_")) or st in {
        "canonical_task",
        "canonical_decision",
        "canonical_project",
    }


def is_vault_contained(*, vault_dir: Path, raw_source_id: str, source_refs: list[str]) -> bool:
    """Real containment check for one retrieved item.

    Returns True only when the raw source_id and every source_ref resolve
    strictly inside vault_dir (no absolute escape, no .. escape, no symlink
    escape outside the vault). Canonical ledger ids (task:/decision:) are
    contained only when their refs are vault-relative and contained.
    """
    try:
        vault_root = vault_dir.resolve()
    except Exception:
        return False
    candidates: list[str] = [raw_source_id, *source_refs]
    for cand in candidates:
        if not cand:
            continue
        c = str(cand)
        # Canonical ledger ids are not filesystem paths; their refs carry containment.
        if c.startswith(("task:", "decision:")):
            continue
        p = Path(c)
        if p.is_absolute():
            try:
                if not p.resolve().is_relative_to(vault_root):
                    return False
            except Exception:
                return False
            continue
        # Relative path must stay inside vault after resolution (handles ..).
        try:
            resolved = (vault_root / p).resolve()
        except Exception:
            return False
        try:
            if not resolved.is_relative_to(vault_root):
                return False
        except Exception:
            return False
        # Explicit .. that escapes the vault root is a scope escape even before resolve.
        # (resolve() above already enforces it; this keeps the intent explicit.)
    return True


def capture_served_default() -> dict[str, str]:
    """Capture the served/default retrieval boundary (measured, never hard-coded)."""
    try:
        from power_framework.core import searcher as _searcher_mod

        _measured_default = str(_searcher_mod.DEFAULT_SEARCH_MODE)
    except Exception:
        _measured_default = "unknown"
    try:
        import inspect as _inspect

        from power_framework.core.application import ApplicationService as _App

        _sig = _inspect.signature(_App.retrieve)
        _retrieve_default = str(_sig.parameters["mode"].default)
        _has_retrieve = "yes"
        _has_compile = "yes" if hasattr(_App, "compile_context") else "no"
    except Exception:
        _retrieve_default = "unknown"
        _has_retrieve = "unknown"
        _has_compile = "unknown"
    return {
        "DEFAULT_SEARCH_MODE": str(_measured_default),
        "retrieve_default_mode": str(_retrieve_default),
        "has_retrieve": str(_has_retrieve),
        "has_compile_context": str(_has_compile),
    }


def compute_dcg(grades: list[float], k: int) -> float:
    """Discounted Cumulative Gain at rank K."""
    dcg = 0.0
    for i, g in enumerate(grades[:k]):
        dcg += (2.0**g - 1.0) / math.log2(i + 2.0)
    return dcg


def compute_ndcg(retrieved: list[str], graded_rel: dict[str, float], k: int) -> float:
    """Normalized Discounted Cumulative Gain at rank K."""
    grades = [graded_rel.get(s, 0.0) for s in retrieved[:k]]
    actual_dcg = compute_dcg(grades, k)
    ideal_grades = sorted(graded_rel.values(), reverse=True)
    ideal_dcg = compute_dcg(ideal_grades, k)
    return (actual_dcg / ideal_dcg) if ideal_dcg > 0 else 1.0


def compute_average_precision(retrieved: list[str], rel_set: set[str]) -> float:
    """Average Precision for a single query."""
    if not rel_set:
        return 1.0
    hits = 0
    ap_sum = 0.0
    for rank, s in enumerate(retrieved, start=1):
        if s in rel_set:
            hits += 1
            ap_sum += hits / rank
    return ap_sum / len(rel_set)


def compute_reciprocal_rank(retrieved: list[str], rel_set: set[str]) -> float:
    """Reciprocal Rank of the first relevant item."""
    for rank, s in enumerate(retrieved, start=1):
        if s in rel_set:
            return 1.0 / rank
    return 0.0


def compute_recall_at_k(retrieved: list[str], rel_set: set[str], k: int) -> float:
    """Recall at rank K."""
    if not rel_set:
        return 1.0
    hits = sum(1 for s in retrieved[:k] if s in rel_set)
    return hits / len(rel_set)


def compute_context_precision(retrieved: list[str], rel_set: set[str], k: int = 10) -> float:
    """Context Precision: proportion of relevant items in top K (frozen: hits / K)."""
    if k <= 0:
        return 0.0
    sub = retrieved[:k]
    hits = sum(1 for s in sub if s in rel_set)
    return hits / float(k)


def setup_benchmark_vault(vault_dir: Path, eval_corpus: Path) -> None:
    """Populate hermetic vault with OKF structure and corpus notes."""
    for d in [
        "01_Projects",
        "02_Areas",
        "03_Resources",
        "04_Archive",
        "05_Templates",
        "06_Daily_Logs",
        ".power",
    ]:
        (vault_dir / d).mkdir(parents=True, exist_ok=True)

    (vault_dir / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Template\n---\n# Template\n", encoding="utf-8"
    )

    domains_yaml = """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: project-state
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: decisions
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: tasks
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: code
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: infrastructure
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: research
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: governance
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
  - name: agent-conversations
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts]
"""
    (vault_dir / ".power" / "domains.yaml").write_text(domains_yaml, encoding="utf-8")

    src_corpus = eval_corpus / "corpus"
    dst_corpus = vault_dir / "01_Projects" / "corpus"
    dst_corpus.mkdir(parents=True, exist_ok=True)

    for md in sorted(src_corpus.glob("*.md")):
        shutil.copy(md, dst_corpus / md.name)


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    query: str
    intent: str
    categories: list[str]
    language_mix: str
    legacy_latency_ms: float
    legacy_retrieved: list[str]
    legacy_scores: list[float]
    legacy_recall: dict[int, float]
    legacy_mrr: float
    legacy_map: float
    legacy_ndcg: dict[int, float]
    legacy_precision: float
    legacy_exclusion_leaks: int
    legacy_authority_violations: int
    shadow_latency_ms: float
    shadow_retrieved: list[str]
    shadow_scores: list[float]
    shadow_authorities: list[str]
    shadow_token_costs: list[int]
    shadow_total_tokens: int
    shadow_pack_bytes: int
    shadow_recall: dict[int, float]
    shadow_mrr: float
    shadow_map: float
    shadow_ndcg: dict[int, float]
    shadow_precision: float
    shadow_exclusion_leaks: int
    shadow_authority_violations: int
    shadow_dense_used: bool
    shadow_reranker_used: bool
    # P38-WP03-R1 correction: ground-truth-aware authority evidence (measured, not hard-coded).
    shadow_expected_winner: str | None
    shadow_winner_present: bool
    shadow_winner_rank: int | None
    shadow_winner_authority: str | None
    shadow_winner_has_canonical_provenance: bool
    shadow_winner_projected_owner: str | None
    shadow_exclusions_above_winner: int
    shadow_authority_outranked: int
    shadow_scope_escapes: int


def run_benchmark(
    *,
    eval_corpus: Path,
    split: str,
    vault_dir: Path,
    expected_revision: str = "v1.1",
    budget_class: str = "FAST",
) -> dict[str, Any]:
    """Execute complete shadow benchmark across all queries in specified split.

    Runner measures runtime, never helps runtime: ground truth scores output
    only; it never creates authority, selects the runtime owner, or changes
    retrieval. Fixture setup copies corpus notes only; any canonical
    Task/Decision/PSE records must be created via production APIs, never via
    fixture-tag-to-authority promotion.
    """
    # P38-WP03-R1 correction: measure served/default retrieval boundary before
    # any retrieval work (never hard-code default_switches = 0).
    # P38-WP03-R3: reproducible dev diagnostics budget class (default FAST).
    normalized_budget = str(budget_class or "FAST").upper()
    if normalized_budget not in {"FAST", "BALANCED", "DEEP"}:
        raise ValueError("budget_class must be FAST, BALANCED, or DEEP")
    served_default_before = capture_served_default()
    setup_benchmark_vault(vault_dir, eval_corpus)

    app = ApplicationService(vault_dir)
    ctx_apply = RequestContext(principal=Principal.local_cli(), authority="apply")
    sync_env = app.sync_vault(fts_only=True, allow_partial=True, context=ctx_apply)
    if sync_env.status != "ok":
        raise RuntimeError(f"Initial benchmark vault sync failed: {sync_env.degraded_reason}")

    # Snapshot baseline vault tree hash for query-side writes audit
    baseline_tree = _hash_vault_tree(vault_dir)

    # Load source metadata
    source_metadata: dict[str, dict[str, Any]] = {}
    with (eval_corpus / "source_metadata.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                source_metadata[rec["source_id"]] = rec

    # Load queries and ground truth for specified split
    queries_path = eval_corpus / f"queries.{split}.jsonl"
    gt_path = eval_corpus / f"ground_truth.{split}.jsonl"

    with queries_path.open("r", encoding="utf-8") as f:
        queries = [json.loads(line) for line in f if line.strip()]

    with gt_path.open("r", encoding="utf-8") as f:
        ground_truth = {
            json.loads(line)["query_id"]: json.loads(line) for line in f if line.strip()
        }

    query_results: list[QueryResult] = []
    total_query_side_writes = 0
    total_determinism_mismatches = 0
    total_scope_escapes = 0
    total_secret_leakages = 0
    total_prompt_injection_escalations = 0

    k_values = [1, 3, 5, 10]
    ndcg_k_values = [5, 10]

    for q in queries:
        qid = q["query_id"]
        gt = ground_truth[qid]

        rel_set = set(gt.get("expected_relevant_source_ids", []))
        excl_set = set(gt.get("expected_exclusion_source_ids", []))
        expected_winner = gt.get("expected_authority_winner")

        graded_rel: dict[str, float] = {}
        for g_item in gt.get("graded_relevance", []):
            graded_rel[g_item["source_id"]] = float(g_item.get("relevance", 1.0))
        for r in rel_set:
            if r not in graded_rel:
                graded_rel[r] = 1.0

        # Legacy Execution
        t0 = time.perf_counter()
        leg_env = app.retrieve(query=q["query"], max_results=20)
        leg_latency = (time.perf_counter() - t0) * 1000.0

        leg_raw_results = leg_env.data.get("results", [])
        leg_retrieved = [normalize_source_id(r["source"]["path"]) for r in leg_raw_results]
        leg_scores = [float(r.get("score", 0.0)) for r in leg_raw_results]

        # Legacy Metrics
        leg_recall = {k: compute_recall_at_k(leg_retrieved, rel_set, k) for k in k_values}
        leg_mrr = compute_reciprocal_rank(leg_retrieved, rel_set)
        leg_map = compute_average_precision(leg_retrieved, rel_set)
        leg_ndcg = {k: compute_ndcg(leg_retrieved, graded_rel, k) for k in ndcg_k_values}
        leg_prec = compute_context_precision(leg_retrieved, rel_set, k=10)
        leg_excl_leaks = sum(1 for s in leg_retrieved[:10] if s in excl_set)

        # Legacy Authority Violations: does any item before expected_winner have lower ground truth authority?
        leg_auth_violations = 0
        if expected_winner and expected_winner in leg_retrieved:
            winner_idx = leg_retrieved.index(expected_winner)
            winner_auth = source_metadata.get(expected_winner, {}).get("authority", "unknown")
            auth_rank = {"canonical": 0, "verified": 1, "curated": 2, "unverified": 3, "unknown": 4}
            for pre_item in leg_retrieved[:winner_idx]:
                pre_auth = source_metadata.get(pre_item, {}).get("authority", "unknown")
                if auth_rank.get(pre_auth, 4) > auth_rank.get(winner_auth, 0):
                    leg_auth_violations += 1

        # Shadow Execution (budget-class is reproducible diagnostics only;
        # it never selects authority or changes retrieval ownership).
        t0 = time.perf_counter()
        shad_env = app.compile_context(
            query=q["query"], intent=q["intent"], budget_class=normalized_budget
        )
        shad_latency = (time.perf_counter() - t0) * 1000.0

        shad_items = shad_env.data.get("items", [])
        shad_raw_ids = [str(item.get("source_id", "")) for item in shad_items]
        shad_retrieved = [normalize_source_id(rid) for rid in shad_raw_ids]
        shad_scores = [float(item.get("score", 0.0)) for item in shad_items]
        shad_authorities = [str(item.get("authority", "unknown")) for item in shad_items]
        shad_bases = [
            str((item.get("provenance") or {}).get("authority_basis", "UNKNOWN"))
            if isinstance(item.get("provenance"), dict)
            else "UNKNOWN"
            for item in shad_items
        ]
        shad_source_types = [str(item.get("source_type", "")) for item in shad_items]
        shad_source_refs_list: list[list[str]] = []
        for item in shad_items:
            prov = item.get("provenance") or {}
            refs = prov.get("source_refs", []) if isinstance(prov, dict) else []
            shad_source_refs_list.append([str(r) for r in refs] if isinstance(refs, list) else [])
        shad_token_costs = [int(item.get("token_cost", 0)) for item in shad_items]
        shad_total_tokens = sum(shad_token_costs)

        shad_pack_bytes = len(json.dumps(shad_env.data, sort_keys=True).encode("utf-8"))

        plan = shad_env.data.get("retrieval_plan", {})
        shad_dense_used = bool(plan.get("dense_used", False))
        shad_reranker_used = bool(plan.get("reranker_used", False))

        # Shadow Metrics (Context Precision frozen formula: hits / K, K=10)
        shad_recall = {k: compute_recall_at_k(shad_retrieved, rel_set, k) for k in k_values}
        shad_mrr = compute_reciprocal_rank(shad_retrieved, rel_set)
        shad_map = compute_average_precision(shad_retrieved, rel_set)
        shad_ndcg = {k: compute_ndcg(shad_retrieved, graded_rel, k) for k in ndcg_k_values}
        shad_prec = compute_context_precision(shad_retrieved, rel_set, k=10)
        shad_excl_leaks = sum(1 for s in shad_retrieved[:10] if s in excl_set)

        # Shadow Authority Order Invariant (legacy internal check, kept for continuity)
        # Invariant: inside ContextPack items, raw/unverified evidence MUST NEVER outrank canonical/verified evidence
        auth_level = {
            "canonical": 0,
            "verified": 1,
            "curated": 2,
            "proposed": 3,
            "unverified": 4,
            "unknown": 5,
        }
        shad_auth_violations = 0
        seen_raw = False
        for it_auth in shad_authorities:
            lvl = auth_level.get(it_auth.lower(), 5)
            if lvl >= 4:  # unverified or unknown
                seen_raw = True
            elif seen_raw and lvl <= 1:  # canonical or verified
                shad_auth_violations += 1

        # P38-WP03-R1 correction: ground-truth-aware authority winner check.
        # GROUND TRUTH SCORES OUTPUT; GROUND TRUTH DOES NOT DRIVE OUTPUT.
        # For each query with expected_authority_winner: verify winner presence,
        # rank, exclusions above, and real canonical runtime provenance.
        # A zero counter that was never measured is not evidence; an all-
        # unverified pack can never PASS an authority-sensitive query.
        shadow_expected_winner = expected_winner
        shadow_winner_present = bool(expected_winner and expected_winner in shad_retrieved)
        shadow_winner_rank: int | None = (
            shad_retrieved.index(expected_winner) + 1
            if shadow_winner_present and expected_winner
            else None
        )
        shadow_winner_authority: str | None = None
        shadow_winner_basis: str = "UNKNOWN"
        shadow_winner_source_type: str = ""
        if shadow_winner_present and expected_winner:
            _widx = shad_retrieved.index(expected_winner)
            shadow_winner_authority = shad_authorities[_widx]
            shadow_winner_basis = shad_bases[_widx]
            shadow_winner_source_type = shad_source_types[_widx]
        shadow_winner_projected_owner: str | None = (
            project_fixture_to_runtime_owner(expected_winner) if expected_winner else None
        )
        shadow_winner_has_canonical_provenance = bool(
            shadow_winner_present
            and shadow_winner_authority is not None
            and has_canonical_runtime_provenance(
                authority=shadow_winner_authority,
                basis=shadow_winner_basis,
                source_type=shadow_winner_source_type,
            )
        )
        # Count expected exclusions (and stale/superseded/hard-negative/raw) above winner.
        shadow_exclusions_above_winner = 0
        shadow_authority_outranked = 0
        if expected_winner:
            _winner_rank0 = (
                shad_retrieved.index(expected_winner)
                if shadow_winner_present
                else len(shad_retrieved)
            )
            for _idx, _sid in enumerate(shad_retrieved[:10]):
                if _idx >= _winner_rank0:
                    break
                if _sid in excl_set:
                    shadow_exclusions_above_winner += 1
            # Authority outranked by relevance is decided after the loop from
            # exclusions-above-winner and canonical-provenance signals.
            # Recompute outranked as: exclusions above + provenance failure signal.
            # If winner is missing, that is an outrank (relevant items outrank absent authority).
            if not shadow_winner_present:
                shadow_authority_outranked = 1
            else:
                shadow_authority_outranked = 1 if shadow_exclusions_above_winner > 0 else 0
                # decision-old MUST NOT outrank decision-current (regression case).
                # Covered generically: expected exclusion above winner => outranked.
                # Canonical provenance failure also means authority was outranked
                # by relevance (all-unverified pack cannot carry authority).
                if not shadow_winner_has_canonical_provenance:
                    shadow_authority_outranked = 1
        # Real scope containment per retrieved item (measured, never constant).
        shadow_scope_escapes = 0
        for _rid, _refs in zip(shad_raw_ids, shad_source_refs_list, strict=True):
            if not is_vault_contained(vault_dir=vault_dir, raw_source_id=_rid, source_refs=_refs):
                shadow_scope_escapes += 1
        total_scope_escapes += shadow_scope_escapes

        # Check prompt injection escalation
        for item in shad_items:
            if "noise-injection" in item.get("source_id", "") and item.get("authority") in {
                "canonical",
                "verified",
            }:
                total_prompt_injection_escalations += 1

        # Check secret leakage
        for item in shad_items:
            for s in ["ghp_", "AddMax13$", "BEGIN PRIVATE KEY"]:
                if s in item.get("excerpt", ""):
                    total_secret_leakages += 1

        # Check determinism: run shadow a second time and verify functional items are identical
        shad_env_2 = app.compile_context(
            query=q["query"], intent=q["intent"], budget_class=normalized_budget
        )
        items_1 = json.dumps(shad_env.data.get("items"), sort_keys=True)
        items_2 = json.dumps(shad_env_2.data.get("items"), sort_keys=True)
        if items_1 != items_2:
            total_determinism_mismatches += 1

        # Query-side write audit after query
        current_tree = _hash_vault_tree(vault_dir)
        if current_tree != baseline_tree:
            total_query_side_writes += 1

        query_results.append(
            QueryResult(
                query_id=qid,
                query=q["query"],
                intent=q["intent"],
                categories=q.get("categories", []),
                language_mix=q.get("language_mix", "EN"),
                legacy_latency_ms=leg_latency,
                legacy_retrieved=leg_retrieved,
                legacy_scores=leg_scores,
                legacy_recall=leg_recall,
                legacy_mrr=leg_mrr,
                legacy_map=leg_map,
                legacy_ndcg=leg_ndcg,
                legacy_precision=leg_prec,
                legacy_exclusion_leaks=leg_excl_leaks,
                legacy_authority_violations=leg_auth_violations,
                shadow_latency_ms=shad_latency,
                shadow_retrieved=shad_retrieved,
                shadow_scores=shad_scores,
                shadow_authorities=shad_authorities,
                shadow_token_costs=shad_token_costs,
                shadow_total_tokens=shad_total_tokens,
                shadow_pack_bytes=shad_pack_bytes,
                shadow_recall=shad_recall,
                shadow_mrr=shad_mrr,
                shadow_map=shad_map,
                shadow_ndcg=shad_ndcg,
                shadow_precision=shad_prec,
                shadow_exclusion_leaks=shad_excl_leaks,
                shadow_authority_violations=shad_auth_violations,
                shadow_dense_used=shad_dense_used,
                shadow_reranker_used=shad_reranker_used,
                shadow_expected_winner=shadow_expected_winner,
                shadow_winner_present=shadow_winner_present,
                shadow_winner_rank=shadow_winner_rank,
                shadow_winner_authority=shadow_winner_authority,
                shadow_winner_has_canonical_provenance=shadow_winner_has_canonical_provenance,
                shadow_winner_projected_owner=shadow_winner_projected_owner,
                shadow_exclusions_above_winner=shadow_exclusions_above_winner,
                shadow_authority_outranked=shadow_authority_outranked,
                shadow_scope_escapes=shadow_scope_escapes,
            )
        )

    # Compute Aggregates
    n = len(query_results)

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = int(len(s) * p)
        return s[min(idx, len(s) - 1)]

    leg_latencies = [qr.legacy_latency_ms for qr in query_results]
    shad_latencies = [qr.shadow_latency_ms for qr in query_results]

    leg_summary = {
        "recall_at_1": _mean([qr.legacy_recall[1] for qr in query_results]),
        "recall_at_3": _mean([qr.legacy_recall[3] for qr in query_results]),
        "recall_at_5": _mean([qr.legacy_recall[5] for qr in query_results]),
        "recall_at_10": _mean([qr.legacy_recall[10] for qr in query_results]),
        "mrr": _mean([qr.legacy_mrr for qr in query_results]),
        "map": _mean([qr.legacy_map for qr in query_results]),
        "ndcg_at_5": _mean([qr.legacy_ndcg[5] for qr in query_results]),
        "ndcg_at_10": _mean([qr.legacy_ndcg[10] for qr in query_results]),
        "context_precision": _mean([qr.legacy_precision for qr in query_results]),
        "exclusion_leaks": sum(qr.legacy_exclusion_leaks for qr in query_results),
        "authority_violations": sum(qr.legacy_authority_violations for qr in query_results),
        "latency_ms_p50": _percentile(leg_latencies, 0.50),
        "latency_ms_p90": _percentile(leg_latencies, 0.90),
        "latency_ms_p95": _percentile(leg_latencies, 0.95),
        "latency_ms_mean": _mean(leg_latencies),
    }

    shad_summary = {
        "recall_at_1": _mean([qr.shadow_recall[1] for qr in query_results]),
        "recall_at_3": _mean([qr.shadow_recall[3] for qr in query_results]),
        "recall_at_5": _mean([qr.shadow_recall[5] for qr in query_results]),
        "recall_at_10": _mean([qr.shadow_recall[10] for qr in query_results]),
        "mrr": _mean([qr.shadow_mrr for qr in query_results]),
        "map": _mean([qr.shadow_map for qr in query_results]),
        "ndcg_at_5": _mean([qr.shadow_ndcg[5] for qr in query_results]),
        "ndcg_at_10": _mean([qr.shadow_ndcg[10] for qr in query_results]),
        "context_precision": _mean([qr.shadow_precision for qr in query_results]),
        "exclusion_leaks": sum(qr.shadow_exclusion_leaks for qr in query_results),
        "authority_violations": sum(qr.shadow_authority_violations for qr in query_results),
        # P38-WP03-R1 correction: ground-truth-aware authority evidence.
        "authority_outranked_by_relevance": sum(
            qr.shadow_authority_outranked for qr in query_results
        ),
        "authority_winner_missing": sum(
            1 for qr in query_results if qr.shadow_expected_winner and not qr.shadow_winner_present
        ),
        "authority_exclusions_above_winner": sum(
            qr.shadow_exclusions_above_winner for qr in query_results
        ),
        "authority_provenance_failures": sum(
            1
            for qr in query_results
            if qr.shadow_expected_winner
            and qr.shadow_winner_present
            and not qr.shadow_winner_has_canonical_provenance
        ),
        "scope_escapes_measured": sum(qr.shadow_scope_escapes for qr in query_results),
        "latency_ms_p50": _percentile(shad_latencies, 0.50),
        "latency_ms_p90": _percentile(shad_latencies, 0.90),
        "latency_ms_p95": _percentile(shad_latencies, 0.95),
        "latency_ms_mean": _mean(shad_latencies),
        "token_accounting": {
            "mean_tokens": _mean([float(qr.shadow_total_tokens) for qr in query_results]),
            "min_tokens": min(qr.shadow_total_tokens for qr in query_results),
            "max_tokens": max(qr.shadow_total_tokens for qr in query_results),
        },
        "context_pack_bytes": {
            "mean_bytes": _mean([float(qr.shadow_pack_bytes) for qr in query_results]),
            "min_bytes": min(qr.shadow_pack_bytes for qr in query_results),
            "max_bytes": max(qr.shadow_pack_bytes for qr in query_results),
        },
        "dense_usage_count": sum(1 for qr in query_results if qr.shadow_dense_used),
        "reranker_usage_count": sum(1 for qr in query_results if qr.shadow_reranker_used),
    }

    comparison = {
        "delta_recall_at_1": shad_summary["recall_at_1"] - leg_summary["recall_at_1"],
        "delta_recall_at_5": shad_summary["recall_at_5"] - leg_summary["recall_at_5"],
        "delta_mrr": shad_summary["mrr"] - leg_summary["mrr"],
        "delta_map": shad_summary["map"] - leg_summary["map"],
        "delta_ndcg_at_10": shad_summary["ndcg_at_10"] - leg_summary["ndcg_at_10"],
        "delta_context_precision": (
            shad_summary["context_precision"] - leg_summary["context_precision"]
        ),
        "delta_exclusion_leaks": shad_summary["exclusion_leaks"] - leg_summary["exclusion_leaks"],
        "delta_authority_violations": (
            shad_summary["authority_violations"] - leg_summary["authority_violations"]
        ),
        "latency_speedup_p50": (
            leg_summary["latency_ms_p50"] / shad_summary["latency_ms_p50"]
            if shad_summary["latency_ms_p50"] > 0
            else 1.0
        ),
    }

    # Group breakdowns
    def _breakdown_by(key_fn: Any) -> dict[str, Any]:
        groups: dict[str, list[QueryResult]] = {}
        for qr in query_results:
            keys = key_fn(qr)
            if not isinstance(keys, list):
                keys = [keys]
            for k in keys:
                groups.setdefault(k, []).append(qr)
        res: dict[str, Any] = {}
        for grp_name, grp_items in sorted(groups.items()):
            res[grp_name] = {
                "query_count": len(grp_items),
                "legacy_mrr": _mean([x.legacy_mrr for x in grp_items]),
                "shadow_mrr": _mean([x.shadow_mrr for x in grp_items]),
                "legacy_map": _mean([x.legacy_map for x in grp_items]),
                "shadow_map": _mean([x.shadow_map for x in grp_items]),
                "legacy_ndcg_at_10": _mean([x.legacy_ndcg[10] for x in grp_items]),
                "shadow_ndcg_at_10": _mean([x.shadow_ndcg[10] for x in grp_items]),
                "legacy_exclusions": sum(x.legacy_exclusion_leaks for x in grp_items),
                "shadow_exclusions": sum(x.shadow_exclusion_leaks for x in grp_items),
            }
        return res

    by_intent = _breakdown_by(lambda qr: qr.intent)
    by_category = _breakdown_by(lambda qr: qr.categories)
    by_language = _breakdown_by(lambda qr: qr.language_mix)

    # P38-WP03-R1 correction: measure served/default boundary after benchmark.
    served_default_after = capture_served_default()
    default_switches_measured = 0 if served_default_after == served_default_before else 1

    hard_invariants = {
        "authority_order_violations": shad_summary["authority_violations"],
        "authority_order_violations_pass": shad_summary["authority_violations"] == 0,
        # Ground-truth-aware authority gate: HARD FAIL when relevance outranks authority.
        "authority_outranked_by_relevance": shad_summary["authority_outranked_by_relevance"],
        "authority_outranked_by_relevance_pass": shad_summary["authority_outranked_by_relevance"]
        == 0,
        "authority_winner_missing": shad_summary["authority_winner_missing"],
        "authority_winner_missing_pass": shad_summary["authority_winner_missing"] == 0,
        "authority_provenance_failures": shad_summary["authority_provenance_failures"],
        "authority_provenance_failures_pass": shad_summary["authority_provenance_failures"] == 0,
        "query_side_writes": total_query_side_writes,
        "query_side_writes_pass": total_query_side_writes == 0,
        "scope_escape": total_scope_escapes,
        "scope_escape_pass": total_scope_escapes == 0,
        "secret_leakage": total_secret_leakages,
        "secret_leakage_pass": total_secret_leakages == 0,
        "prompt_injection_authority_escalation": total_prompt_injection_escalations,
        "prompt_injection_authority_escalation_pass": total_prompt_injection_escalations == 0,
        "determinism_mismatches": total_determinism_mismatches,
        "determinism_mismatches_pass": total_determinism_mismatches == 0,
        "default_switches": default_switches_measured,
        "default_switches_pass": default_switches_measured == 0,
        "served_default_before": served_default_before,
        "served_default_after": served_default_after,
    }

    all_invariants_pass = all(v is True for k, v in hard_invariants.items() if k.endswith("_pass"))

    return {
        "benchmark_metadata": {
            "schema_version": "power.retrieval-benchmark-shadow.v1",
            "runner_correction": "P38-WP03-R1",
            "runner_authority_correction": "P38-WP03-R3",
            "budget_class": normalized_budget,
            "timestamp": datetime.now(UTC).isoformat(),
            "split": split,
            "eval_corpus_version": expected_revision,
            "query_count": n,
            "platform": platform.platform(),
            "python_version": sys.version,
            "all_hard_invariants_pass": all_invariants_pass,
            "HOLDOUT_PREVIOUSLY_EXPOSED": True,
            "RUNTIME_TUNING_AFTER_HOLDOUT": False,
        },
        "summary": {
            "legacy": leg_summary,
            "shadow": shad_summary,
            "comparison": comparison,
        },
        "breakdowns": {
            "by_intent": by_intent,
            "by_category": by_category,
            "by_language": by_language,
        },
        "hard_invariants": hard_invariants,
        "queries": [
            {
                "query_id": qr.query_id,
                "query": qr.query,
                "intent": qr.intent,
                "categories": qr.categories,
                "language_mix": qr.language_mix,
                "legacy": {
                    "latency_ms": round(qr.legacy_latency_ms, 2),
                    "retrieved": qr.legacy_retrieved,
                    "scores": qr.legacy_scores,
                    "recall": qr.legacy_recall,
                    "mrr": round(qr.legacy_mrr, 4),
                    "map": round(qr.legacy_map, 4),
                    "ndcg": {k: round(v, 4) for k, v in qr.legacy_ndcg.items()},
                    "precision": round(qr.legacy_precision, 4),
                    "exclusion_leaks": qr.legacy_exclusion_leaks,
                    "authority_violations": qr.legacy_authority_violations,
                },
                "shadow": {
                    "latency_ms": round(qr.shadow_latency_ms, 2),
                    "retrieved": qr.shadow_retrieved,
                    "scores": qr.shadow_scores,
                    "authorities": qr.shadow_authorities,
                    "total_tokens": qr.shadow_total_tokens,
                    "pack_bytes": qr.shadow_pack_bytes,
                    "dense_used": qr.shadow_dense_used,
                    "reranker_used": qr.shadow_reranker_used,
                    "recall": qr.shadow_recall,
                    "mrr": round(qr.shadow_mrr, 4),
                    "map": round(qr.shadow_map, 4),
                    "ndcg": {k: round(v, 4) for k, v in qr.shadow_ndcg.items()},
                    "precision": round(qr.shadow_precision, 4),
                    "exclusion_leaks": qr.shadow_exclusion_leaks,
                    "authority_violations": qr.shadow_authority_violations,
                    "expected_authority_winner": qr.shadow_expected_winner,
                    "winner_present": qr.shadow_winner_present,
                    "winner_rank": qr.shadow_winner_rank,
                    "winner_authority": qr.shadow_winner_authority,
                    "winner_has_canonical_provenance": qr.shadow_winner_has_canonical_provenance,
                    "winner_projected_owner": qr.shadow_winner_projected_owner,
                    "exclusions_above_winner": qr.shadow_exclusions_above_winner,
                    "authority_outranked": qr.shadow_authority_outranked,
                    "scope_escapes": qr.shadow_scope_escapes,
                },
            }
            for qr in query_results
        ],
    }


def generate_protocol_freeze(
    *,
    eval_corpus: Path,
    runner_path: Path,
    output_path: Path,
    expected_revision: str = "v1.1",
) -> dict[str, Any]:
    """Freeze benchmark protocol, formulas, digest contracts and thresholds."""
    manifest_path = eval_corpus / "manifest.json"
    manifest_digest = _sha256_file(manifest_path)

    disjointness_path = eval_corpus / "disjointness-proof.json"
    disjointness_digest = _sha256_file(disjointness_path)

    runner_digest = _sha256_file(runner_path)

    freeze_data = {
        "protocol_version": "power.retrieval-benchmark-protocol-freeze.v1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "evaluation_corpus_revision": expected_revision,
        "corpus_manifest_sha256": manifest_digest,
        "corpus_disjointness_proof_sha256": disjointness_digest,
        "runner_implementation_sha256": runner_digest,
        "metric_formulas": {
            "Recall@K": "sum_{i=1..K}(rel(item_i)) / |relevant_set|",
            "MRR": "1.0 / rank_of_first_relevant_item (0 if none retrieved)",
            "MAP": "sum_{k=1..N}(Precision@k * rel(item_k)) / |relevant_set|",
            "nDCG@K": "DCG@K / IDCG@K where DCG@K = sum_{i=1..K}(2^{rel_i} - 1) / log2(i + 1)",
            "Context_Precision": "sum_{i=1..K}(rel(item_i)) / K (where K=10)",
        },
        "k_values": [1, 3, 5, 10],
        "ndcg_k_values": [5, 10],
        "hard_invariant_gates": {
            "authority_order_violations": "MUST == 0 in Shadow mode (CANONICAL > VERIFIED > CURATED > UNVERIFIED)",
            "query_side_writes": "MUST == 0 (SHA-256 vault tree unmodified across all queries)",
            "scope_escape": "MUST == 0 (all items remain strictly vault-contained)",
            "secret_leakage": "MUST == 0 (zero unredacted tokens, passwords or private keys)",
            "prompt_injection_authority_escalation": "MUST == 0 (zero injection text gains authority)",
            "determinism_mismatches": "MUST == 0 (consecutive identical queries produce bit-identical packs)",
            "default_switches": "MUST == 0 (Legacy retrieval remains served default)",
        },
        "minimum_quality_gates": {
            "Recall@5": ">= 0.70",
            "MRR": ">= 0.50",
            "nDCG@10": ">= 0.60",
        },
        "governance": {
            "operator": "weby-homelab <rekvizitor.ua@gmail.com>",
            "gpg_key_id": "2D49E810C7F2527E",
            "phase": "Phase 5E / P38-WP03",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(freeze_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return freeze_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus",
        type=Path,
        default=Path("benchmarks/power38/retrieval_eval/v1.1"),
        help="path to frozen retrieval evaluation corpus (default: v1.1)",
    )
    parser.add_argument(
        "--split",
        choices=("development", "holdout"),
        default="development",
        help="corpus split to evaluate (default: development)",
    )
    parser.add_argument(
        "--vault-dir",
        type=Path,
        help="optional persistent vault directory; if omitted, creates a temporary vault",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional output path for benchmark JSON results",
    )
    parser.add_argument(
        "--budget-class",
        choices=("FAST", "BALANCED", "DEEP"),
        default="FAST",
        help="reproducible dev diagnostics budget class (default: FAST)",
    )
    parser.add_argument(
        "--freeze-protocol",
        type=Path,
        help="optional output path to generate protocol freeze JSON",
    )

    args = parser.parse_args(argv)

    eval_corpus = args.eval_corpus.resolve()
    if not eval_corpus.is_dir():
        print(f"Error: evaluation corpus directory does not exist: {eval_corpus}", file=sys.stderr)
        return 1

    # Freeze protocol if requested
    if args.freeze_protocol:
        runner_path = Path(__file__).resolve()
        generate_protocol_freeze(
            eval_corpus=eval_corpus,
            runner_path=runner_path,
            output_path=args.freeze_protocol.resolve(),
        )
        print(f"Protocol freeze written to {args.freeze_protocol.resolve()}")

    # Prepare vault
    is_temp_vault = False
    if args.vault_dir:
        vault_dir = args.vault_dir.resolve()
        vault_dir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_obj = tempfile.TemporaryDirectory()
        vault_dir = Path(tmp_obj.name) / "benchmark_vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        is_temp_vault = True

    try:
        results = run_benchmark(
            eval_corpus=eval_corpus,
            split=args.split,
            vault_dir=vault_dir,
            budget_class=args.budget_class,
        )

        # Write output if requested
        if args.output:
            out_path = args.output.resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"Benchmark results written to {out_path}")

        # Print Executive Summary
        leg = results["summary"]["legacy"]
        shad = results["summary"]["shadow"]
        comp = results["summary"]["comparison"]
        invars = results["hard_invariants"]

        print("\n========================================================")
        print(f"POWER 3.8 Phase 5E — Shadow Benchmark ({args.split.upper()})")
        print("========================================================")
        print("Quality Metrics          Legacy       Shadow       Delta")
        print("--------------------------------------------------------")
        print(
            f"Recall@1                 {leg['recall_at_1']:.4f}       {shad['recall_at_1']:.4f}       {comp['delta_recall_at_1']:+.4f}"
        )
        print(
            f"Recall@3                 {leg['recall_at_3']:.4f}       {shad['recall_at_3']:.4f}       {(shad['recall_at_3'] - leg['recall_at_3']):+.4f}"
        )
        print(
            f"Recall@5                 {leg['recall_at_5']:.4f}       {shad['recall_at_5']:.4f}       {comp['delta_recall_at_5']:+.4f}"
        )
        print(
            f"Recall@10                {leg['recall_at_10']:.4f}       {shad['recall_at_10']:.4f}       {(shad['recall_at_10'] - leg['recall_at_10']):+.4f}"
        )
        print(
            f"MRR                      {leg['mrr']:.4f}       {shad['mrr']:.4f}       {comp['delta_mrr']:+.4f}"
        )
        print(
            f"MAP                      {leg['map']:.4f}       {shad['map']:.4f}       {comp['delta_map']:+.4f}"
        )
        print(
            f"nDCG@5                   {leg['ndcg_at_5']:.4f}       {shad['ndcg_at_5']:.4f}       {(shad['ndcg_at_5'] - leg['ndcg_at_5']):+.4f}"
        )
        print(
            f"nDCG@10                  {leg['ndcg_at_10']:.4f}       {shad['ndcg_at_10']:.4f}       {comp['delta_ndcg_at_10']:+.4f}"
        )
        print(
            f"Context Precision        {leg['context_precision']:.4f}       {shad['context_precision']:.4f}       {comp['delta_context_precision']:+.4f}"
        )
        print(
            f"Exclusion Leaks          {leg['exclusion_leaks']}            {shad['exclusion_leaks']}            {comp['delta_exclusion_leaks']:+d}"
        )
        print(
            f"Authority Violations     {leg['authority_violations']}            {shad['authority_violations']}            {comp['delta_authority_violations']:+d}"
        )
        print("--------------------------------------------------------")
        print(
            f"Latency p50 (ms)         {leg['latency_ms_p50']:.1f}        {shad['latency_ms_p50']:.1f}        {comp['latency_speedup_p50']:.2f}x speedup"
        )
        print(
            f"Latency p95 (ms)         {leg['latency_ms_p95']:.1f}        {shad['latency_ms_p95']:.1f}"
        )
        print(f"ContextPack Tokens (mean): {shad['token_accounting']['mean_tokens']:.1f}")
        print(f"ContextPack Bytes (mean):  {shad['context_pack_bytes']['mean_bytes']:.1f}")
        print("--------------------------------------------------------")
        print("Hard Invariants Check:")
        for k, v in sorted(invars.items()):
            if k.endswith("_pass"):
                inv_name = k.removesuffix("_pass")
                status_str = "PASS" if v else "FAIL"
                val = invars[inv_name]
                print(f"  {inv_name:36}: {val} [{status_str}]")
        print("========================================================\n")

        if not results["benchmark_metadata"]["all_hard_invariants_pass"]:
            print("ERROR: One or more hard invariants failed!", file=sys.stderr)
            return 2

        return 0
    finally:
        if is_temp_vault:
            with contextlib.suppress(Exception):
                tmp_obj.cleanup()


if __name__ == "__main__":
    sys.exit(main())
