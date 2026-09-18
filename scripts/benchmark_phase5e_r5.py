#!/usr/bin/env python3
"""POWER 3.8 Phase 5E R5 — production-faithful evaluation runner.

RUNTIME != BENCHMARK. This runner MODELS production, it never modifies
production retrieval to fit the benchmark.

Layer A (canonical production state) is created through real production APIs
(TaskService / DecisionService / ProjectEventStore trusted writer) before any
query measurement. Layer B (evidence corpus) is synthetic Markdown loaded as
UNVERIFIED / PROPOSED / RAW unless an independent production owner proves
otherwise.

Concept identity (eval_concept_id) maps file representations and runtime
representations to one semantic concept for scoring ONLY. The mapping never
enters RetrievalPlanner, never changes ranking, never grants authority, and
never reaches ApplicationService input.

Setup writes are allowed. Query phase is strictly read-only
(query_side_writes MUST == 0).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import platform
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from benchmark_phase5e_shadow import (  # noqa: E402
    _hash_vault_tree,
    _sha256_file,
    capture_served_default,
    compute_average_precision,
    compute_context_precision,
    compute_ndcg,
    compute_recall_at_k,
    compute_reciprocal_rank,
    has_canonical_runtime_provenance,
    is_vault_contained,
    normalize_source_id,
    setup_benchmark_vault,
)
from phase5e_concept_mapping_r5 import (  # noqa: E402
    build_alias_to_concept,
    is_owner_backed,
    load_manifest,
    owner_for_concept,
    source_id_to_concept,
)


def compute_setup_state_digest(vault_dir: Path) -> str:
    """Deterministic setup-state digest over sorted vault tree hashes."""
    tree = _hash_vault_tree(vault_dir)
    lines = [f"{rel}:{tree[rel]}" for rel in sorted(tree)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def setup_production_fixtures(vault_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Create Layer A canonical fixtures through real production APIs only.

    Order: Task -> Decision (binds task revision) -> Projects (PSE ledger).
    No Markdown frontmatter, tags, paths, or benchmark labels grant authority.
    Returns receipts with runtime IDs, revisions, and state revisions.
    """
    from power_framework.core.decision_service import DecisionService
    from power_framework.core.project_models import AppendCommand
    from power_framework.core.project_store import ProjectEventStore
    from power_framework.core.state_service import ProjectStateService
    from power_framework.core.task_service import TaskService

    vault_dir = Path(vault_dir)
    concepts = {c["eval_concept_id"]: c for c in manifest.get("concepts", [])}
    receipts: dict[str, Any] = {"tasks": {}, "decisions": {}, "projects": {}}

    ts = TaskService(vault_dir)
    ds = DecisionService(vault_dir, task_service=ts)

    # 1. Task fixture (must exist before decision binding).
    task_concept = concepts.get("task-current", {})
    task_payload = task_concept.get("setup_payload") or {}
    task_id = str(task_payload.get("task_id", "p38-task-current-corpus-verify"))
    existing = None
    with contextlib.suppress(Exception):
        existing = ts.get_task(task_id)
    if existing is None:
        created_task = ts.create_task(
            task_id=task_id,
            title=str(task_payload.get("title", "Verify corpus task")),
            objective=str(task_payload.get("objective", "Verify corpus")),
            owner="fixture-setup",
            state=str(task_payload.get("state", "ready")),  # type: ignore[arg-type]
            actor="fixture-setup",
        )
        receipts["tasks"][task_id] = {
            "revision": int(getattr(created_task, "revision", 1)),
            "title": created_task.title,
        }
    else:
        receipts["tasks"][task_id] = {
            "revision": int(getattr(existing, "revision", 1)),
            "title": getattr(existing, "title", ""),
        }

    # 2. Decision fixture (binds current task revision).
    dec_concept = concepts.get("decision-current", {})
    dec_payload = dec_concept.get("setup_payload") or {}
    dec_id = str(dec_payload.get("decision_id", "dec_x-current-holdout-tuning-decision"))
    dec_task_id = str(dec_payload.get("task_id", task_id))
    existing_dec = None
    with contextlib.suppress(Exception):
        existing_dec = ds.get_decision(dec_id)
    if existing_dec is None:
        created_dec = ds.create_decision(
            decision_id=dec_id,
            task_id=dec_task_id,
            title=str(dec_payload.get("title", "Canonical decision")),
            requested_by=str(dec_payload.get("requested_by", "fixture-setup")),
            description=str(dec_payload.get("description", "")),
            allowed_actors=["fixture-setup"],
        )
        receipts["decisions"][dec_id] = {
            "task_id": dec_task_id,
            "task_revision": int(getattr(created_dec, "task_revision", 1)),
            "title": created_dec.title,
        }
    else:
        receipts["decisions"][dec_id] = {
            "task_id": getattr(existing_dec, "task_id", dec_task_id),
            "task_revision": int(getattr(existing_dec, "task_revision", 1)),
            "title": getattr(existing_dec, "title", ""),
        }

    # 3. Project fixtures via trusted PSE writer (dynamically from manifest).
    pss = ProjectStateService(vault_dir, task_service=ts, decision_service=ds)
    for concept in manifest.get("concepts", []):
        if concept.get("production_owner") == "ProjectStateService" and concept.get(
            "setup_payload"
        ):
            concept_id = concept["eval_concept_id"]
            payload = concept["setup_payload"]
            project_id = str(payload.get("project_id", concept.get("runtime_object_id", "")))
            if not project_id:
                continue
            store = ProjectEventStore(project_id, vault_dir)
            events = payload.get("events", [])
            if not events:
                events = [
                    {
                        "event_type": "project.created",
                        "payload": {"name": project_id},
                        "actor": "fixture-setup",
                    }
                ]
            for ev in events:
                cmd = AppendCommand(
                    project_id=project_id,
                    event_type=str(ev.get("event_type", "project.created")),
                    payload=dict(ev.get("payload", {})),
                    actor=str(ev.get("actor", "fixture-setup")),
                    source="pse_governance",
                )
                with contextlib.suppress(Exception):
                    head_exists = False
                    try:
                        files = store.list_event_files()
                        head_exists = len(files) > 0
                    except Exception:
                        head_exists = False
                    if not head_exists:
                        store._append_governed(cmd)
                    else:
                        break
            state = pss.rebuild_project_state(project_id)
            receipts["projects"][project_id] = {
                "eval_concept_id": concept_id,
                "state_revision": str(getattr(state, "state_revision", "")),
            }

    return receipts


def _concepts_of(raw_ids: list[str], alias_lookup: dict[str, str]) -> list[str | None]:
    return [source_id_to_concept(rid, alias_lookup) for rid in raw_ids]


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def run_benchmark_r5(
    *,
    eval_corpus: Path,
    split: str,
    vault_dir: Path,
    manifest_path: Path,
    expected_revision: str = "v1.1",
    budget_class: str = "FAST",
) -> dict[str, Any]:
    """Execute production-faithful benchmark with concept-aware scoring."""
    from power_framework.core.application import ApplicationService
    from power_framework.core.principal import Principal

    eval_corpus = Path(eval_corpus).resolve()
    vault_dir = Path(vault_dir).resolve()
    manifest_path = Path(manifest_path).resolve()

    manifest = load_manifest(manifest_path)
    alias_lookup = build_alias_to_concept(manifest)
    manifest_sha = _sha256_file(manifest_path)
    runner_sha = _sha256_file(Path(__file__).resolve())

    served_default_before = capture_served_default()

    # Ephemeral vault: 1. structure + Markdown corpus, 2. canonical fixtures,
    # 3. search index, 4. freeze + hash, 5. only then measure queries.
    setup_benchmark_vault(vault_dir, eval_corpus)
    receipts = setup_production_fixtures(vault_dir, manifest)

    app = ApplicationService(vault_dir)
    from power_framework.core.application import RequestContext

    ctx_apply = RequestContext(principal=Principal.local_cli(), authority="apply")
    sync_env = app.sync_vault(fts_only=True, allow_partial=True, context=ctx_apply)
    if sync_env.status != "ok":
        raise RuntimeError(f"R5 benchmark vault sync failed: {sync_env.degraded_reason}")

    baseline_tree = _hash_vault_tree(vault_dir)
    setup_state_digest = compute_setup_state_digest(vault_dir)

    # Step 4: Load queries and ground truth for the split.
    queries_file = eval_corpus / f"queries.{split}.jsonl"
    gt_file = eval_corpus / f"ground_truth.{split}.jsonl"
    queries = [
        json.loads(line)
        for line in queries_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ground_truth = {
        item["query_id"]: item
        for item in (
            json.loads(line)
            for line in gt_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    k_values = [1, 3, 5, 10]
    ndcg_k_values = [5, 10]
    query_results: list[dict[str, Any]] = []

    total_query_side_writes = 0
    total_scope_escapes = 0
    total_secret_leakages = 0
    total_prompt_injection_escalations = 0
    total_determinism_mismatches = 0
    discriminator_checks: list[dict[str, Any]] = []

    normalized_budget = budget_class.upper()

    for q in queries:
        qid = q["query_id"]
        gt = ground_truth.get(qid, {})
        rel_files = [normalize_source_id(s) for s in gt.get("expected_relevant_source_ids", [])]
        excl_files = [normalize_source_id(s) for s in gt.get("expected_exclusion_source_ids", [])]
        expected_winner_file = gt.get("expected_authority_winner")
        expected_concept = (
            source_id_to_concept(normalize_source_id(expected_winner_file), alias_lookup)
            if expected_winner_file
            else None
        )
        owner_backed_query = bool(
            expected_concept and is_owner_backed(str(expected_concept), manifest)
        )

        rel_concepts = _dedup_preserve_order(
            [c for c in _concepts_of(rel_files, alias_lookup) if c is not None]
        )
        excl_concepts = _dedup_preserve_order(
            [c for c in _concepts_of(excl_files, alias_lookup) if c is not None]
        )
        graded_rel: dict[str, float] = {}
        for g in gt.get("graded_relevance", []):
            cid = source_id_to_concept(normalize_source_id(g["source_id"]), alias_lookup)
            if cid:
                graded_rel[cid] = max(graded_rel.get(cid, 0.0), float(g["relevance"]))
        for r in rel_concepts:
            if r not in graded_rel:
                graded_rel[str(r)] = 1.0

        # Legacy retrieval (concept-mapped for non-regression fairness).
        leg_t0 = time.perf_counter()
        leg_env = app.retrieve(query=q["query"], max_results=20)
        leg_latency = (time.perf_counter() - leg_t0) * 1000.0
        leg_raw = leg_env.data.get("results", [])
        leg_raw_ids = [str(r["source"]["path"]) for r in leg_raw]
        leg_stems = [normalize_source_id(r) for r in leg_raw_ids]
        leg_concepts = _dedup_preserve_order(
            [source_id_to_concept(s, alias_lookup) or s for s in leg_stems]
        )
        leg_recall = {k: compute_recall_at_k(leg_concepts, rel_concepts, k) for k in k_values}
        leg_mrr = compute_reciprocal_rank(leg_concepts, rel_concepts)
        leg_map = compute_average_precision(leg_concepts, rel_concepts)
        leg_ndcg = {k: compute_ndcg(leg_concepts, graded_rel, k) for k in ndcg_k_values}
        leg_prec = compute_context_precision(leg_concepts, rel_concepts, k=10)

        # Shadow retrieval (RetrievalPlanner context compilation).
        shad_t0 = time.perf_counter()
        shad_env = app.compile_context(
            query=q["query"], intent=q["intent"], budget_class=normalized_budget
        )
        shad_latency = (time.perf_counter() - shad_t0) * 1000.0
        shad_items = shad_env.data.get("items", [])
        shad_raw_ids = [str(item.get("source_id", "")) for item in shad_items]
        shad_stems = [normalize_source_id(rid) for rid in shad_raw_ids]
        shad_concepts_raw: list[str] = [
            source_id_to_concept(s, alias_lookup) or s for s in shad_stems
        ]
        for idx, rid in enumerate(shad_raw_ids):
            mapped_full = source_id_to_concept(rid, alias_lookup)
            if mapped_full:
                shad_concepts_raw[idx] = mapped_full
        shad_concepts: list[str] = _dedup_preserve_order(shad_concepts_raw)
        shad_authorities = [str(item.get("authority", "unknown")) for item in shad_items]
        shad_bases = [
            str((item.get("provenance") or {}).get("authority_basis", "UNKNOWN"))
            if isinstance(item.get("provenance"), dict)
            else "UNKNOWN"
            for item in shad_items
        ]
        shad_source_types = [str(item.get("source_type", "")) for item in shad_items]
        shad_refs: list[list[str]] = []
        for item in shad_items:
            prov = item.get("provenance") or {}
            refs = prov.get("source_refs", []) if isinstance(prov, dict) else []
            shad_refs.append([str(r) for r in refs] if isinstance(refs, list) else [])
        shad_token_costs = [int(item.get("token_cost", 0)) for item in shad_items]
        shad_total_tokens = sum(shad_token_costs)
        shad_pack_bytes = len(json.dumps(shad_env.data, sort_keys=True).encode("utf-8"))
        plan = shad_env.data.get("retrieval_plan", {})
        shad_dense_used = bool(plan.get("dense_used", False))
        shad_reranker_used = bool(plan.get("reranker_used", False))

        shad_recall = {k: compute_recall_at_k(shad_concepts, rel_concepts, k) for k in k_values}
        shad_mrr = compute_reciprocal_rank(shad_concepts, rel_concepts)
        shad_map = compute_average_precision(shad_concepts, rel_concepts)
        shad_ndcg = {k: compute_ndcg(shad_concepts, graded_rel, k) for k in ndcg_k_values}
        shad_prec = compute_context_precision(shad_concepts, rel_concepts, k=10)
        shad_excl_leaks = sum(1 for s in shad_concepts[:10] if s in excl_concepts)

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
            if lvl >= 4:
                seen_raw = True
            elif seen_raw and lvl <= 1:
                shad_auth_violations += 1

        # Concept-aware authority winner check (owner-backed only for gates).
        winner_present = False
        winner_rank: int | None = None
        winner_authority: str | None = None
        winner_projected_owner: str | None = None
        winner_has_provenance = True
        exclusions_above = 0
        outranked = 0
        if expected_concept:
            winner_projected_owner = owner_for_concept(str(expected_concept), manifest)
            if owner_backed_query:
                if str(expected_concept) in shad_concepts:
                    winner_present = True
                    widx = shad_concepts.index(str(expected_concept))
                    winner_rank = widx + 1
                    raw_idx = shad_concepts_raw.index(str(expected_concept))
                    winner_authority = shad_authorities[raw_idx]
                    winner_basis = shad_bases[raw_idx]
                    winner_source_type = shad_source_types[raw_idx]
                    winner_has_provenance = has_canonical_runtime_provenance(
                        authority=winner_authority or "unknown",
                        basis=winner_basis,
                        source_type=winner_source_type,
                    )
                # Exclusions above winner (concept space, top-10).
                rank0 = (
                    shad_concepts.index(str(expected_concept))
                    if winner_present
                    else len(shad_concepts)
                )
                for idx2, sid in enumerate(shad_concepts[:10]):
                    if idx2 >= rank0:
                        break
                    if sid in excl_concepts:
                        exclusions_above += 1
                if not winner_present or exclusions_above > 0 or not winner_has_provenance:
                    outranked = 1
            else:
                # VaultNote / Quarantine: no CANONICAL requirement.
                winner_present = str(expected_concept) in shad_concepts
                if winner_present:
                    widx = shad_concepts.index(str(expected_concept))
                    winner_rank = widx + 1
                    raw_idx = shad_concepts_raw.index(str(expected_concept))
                    winner_authority = shad_authorities[raw_idx]
                winner_has_provenance = True
                exclusions_above = 0
                outranked = 0

        # Discriminator evidence for owner-backed concepts.
        if owner_backed_query and expected_concept:
            runtime_alias_hits = [
                (rid, shad_authorities[i])
                for i, rid in enumerate(shad_raw_ids)
                if rid.startswith(("task:", "decision:", "project:"))
                and source_id_to_concept(rid, alias_lookup) == str(expected_concept)
            ]
            file_alias_hits = [
                (rid, shad_authorities[i])
                for i, rid in enumerate(shad_raw_ids)
                if not rid.startswith(("task:", "decision:", "project:"))
                and source_id_to_concept(rid, alias_lookup) == str(expected_concept)
            ]
            discriminator_checks.append(
                {
                    "query_id": qid,
                    "concept": str(expected_concept),
                    "runtime_hits_canonical": sum(
                        1 for _, a in runtime_alias_hits if a == "canonical"
                    ),
                    "file_hits_not_canonical": sum(
                        1 for _, a in file_alias_hits if a != "canonical"
                    ),
                }
            )

        scope_escapes = 0
        for rid, refs in zip(shad_raw_ids, shad_refs, strict=True):
            if not is_vault_contained(vault_dir=vault_dir, raw_source_id=rid, source_refs=refs):
                scope_escapes += 1
        total_scope_escapes += scope_escapes

        for item in shad_items:
            if "noise-injection" in item.get("source_id", "") and item.get("authority") in {
                "canonical",
                "verified",
            }:
                total_prompt_injection_escalations += 1
        for item in shad_items:
            for s in ["ghp_", "AddMax13$", "BEGIN PRIVATE KEY"]:
                if s in item.get("excerpt", ""):
                    total_secret_leakages += 1

        shad_env_2 = app.compile_context(
            query=q["query"], intent=q["intent"], budget_class=normalized_budget
        )
        if json.dumps(shad_env.data.get("items"), sort_keys=True) != json.dumps(
            shad_env_2.data.get("items"), sort_keys=True
        ):
            total_determinism_mismatches += 1

        if _hash_vault_tree(vault_dir) != baseline_tree:
            total_query_side_writes += 1

        query_results.append(
            {
                "query_id": qid,
                "expected_concept": expected_concept,
                "owner_backed": owner_backed_query,
                "projected_owner": winner_projected_owner,
                "legacy": {
                    "latency_ms": round(leg_latency, 2),
                    "concepts": leg_concepts,
                    "recall": leg_recall,
                    "mrr": round(leg_mrr, 4),
                    "map": round(leg_map, 4),
                    "ndcg": {str(k): round(v, 4) for k, v in leg_ndcg.items()},
                    "precision": round(leg_prec, 4),
                },
                "shadow": {
                    "latency_ms": round(shad_latency, 2),
                    "concepts": shad_concepts,
                    "raw_source_ids": shad_raw_ids,
                    "authorities": shad_authorities,
                    "recall": shad_recall,
                    "mrr": round(shad_mrr, 4),
                    "map": round(shad_map, 4),
                    "ndcg": {str(k): round(v, 4) for k, v in shad_ndcg.items()},
                    "precision": round(shad_prec, 4),
                    "exclusion_leaks": shad_excl_leaks,
                    "authority_violations": shad_auth_violations,
                    "winner_present": winner_present,
                    "winner_rank": winner_rank,
                    "winner_authority": winner_authority,
                    "winner_has_canonical_provenance": winner_has_provenance,
                    "exclusions_above_winner": exclusions_above,
                    "authority_outranked": outranked,
                    "token_cost": shad_total_tokens,
                    "pack_bytes": shad_pack_bytes,
                    "dense_used": shad_dense_used,
                    "reranker_used": shad_reranker_used,
                },
            }
        )

    def _mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def _pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = round(p * (len(s) - 1))
        return round(s[idx], 2)

    leg_lat = [q["legacy"]["latency_ms"] for q in query_results]
    shad_lat = [q["shadow"]["latency_ms"] for q in query_results]

    leg_summary = {
        "recall_at_1": _mean([q["legacy"]["recall"][1] for q in query_results]),
        "recall_at_3": _mean([q["legacy"]["recall"][3] for q in query_results]),
        "recall_at_5": _mean([q["legacy"]["recall"][5] for q in query_results]),
        "recall_at_10": _mean([q["legacy"]["recall"][10] for q in query_results]),
        "mrr": _mean([q["legacy"]["mrr"] for q in query_results]),
        "map": _mean([q["legacy"]["map"] for q in query_results]),
        "ndcg_at_10": _mean([q["legacy"]["ndcg"]["10"] for q in query_results]),
        "context_precision": _mean([q["legacy"]["precision"] for q in query_results]),
        "latency_ms_p50": _pct(leg_lat, 0.50),
        "latency_ms_p95": _pct(leg_lat, 0.95),
    }

    owner_results = [q for q in query_results if q["owner_backed"]]
    total_query_count = len(query_results)
    applicable_owner_count = len(owner_results)
    not_applicable_owner_count = total_query_count - applicable_owner_count

    winner_missing_count = sum(1 for q in owner_results if not q["shadow"]["winner_present"])
    auth_winner_missing_metric = {
        "applicable_query_count": applicable_owner_count,
        "measured_violation_count": winner_missing_count,
        "not_applicable_count": not_applicable_owner_count,
        "pass": winner_missing_count == 0,
    }

    applicable_prov_queries = [q for q in owner_results if q["shadow"]["winner_present"]]
    prov_failures_count = sum(
        1 for q in applicable_prov_queries if not q["shadow"]["winner_has_canonical_provenance"]
    )
    auth_provenance_metric = {
        "applicable_query_count": len(applicable_prov_queries),
        "measured_violation_count": prov_failures_count,
        "not_applicable_count": total_query_count - len(applicable_prov_queries),
        "pass": prov_failures_count == 0,
    }

    outranked_count = sum(q["shadow"]["authority_outranked"] for q in owner_results)
    auth_outranked_metric = {
        "applicable_query_count": applicable_owner_count,
        "measured_violation_count": outranked_count,
        "not_applicable_count": not_applicable_owner_count,
        "pass": outranked_count == 0,
    }

    total_order_violations = sum(q["shadow"]["authority_violations"] for q in query_results)
    auth_order_metric = {
        "applicable_query_count": total_query_count,
        "measured_violation_count": total_order_violations,
        "not_applicable_count": 0,
        "pass": total_order_violations == 0,
    }

    shad_summary = {
        "recall_at_1": _mean([q["shadow"]["recall"][1] for q in query_results]),
        "recall_at_3": _mean([q["shadow"]["recall"][3] for q in query_results]),
        "recall_at_5": _mean([q["shadow"]["recall"][5] for q in query_results]),
        "recall_at_10": _mean([q["shadow"]["recall"][10] for q in query_results]),
        "mrr": _mean([q["shadow"]["mrr"] for q in query_results]),
        "map": _mean([q["shadow"]["map"] for q in query_results]),
        "ndcg_at_10": _mean([q["shadow"]["ndcg"]["10"] for q in query_results]),
        "context_precision": _mean([q["shadow"]["precision"] for q in query_results]),
        "latency_ms_p50": _pct(shad_lat, 0.50),
        "latency_ms_p95": _pct(shad_lat, 0.95),
        "authority_violations": total_order_violations,
        "authority_winner_missing": winner_missing_count,
        "authority_provenance_failures": prov_failures_count,
        "authority_outranked_by_relevance": outranked_count,
        "authority_exclusions_above_winner": sum(
            q["shadow"]["exclusions_above_winner"] for q in owner_results
        ),
        "owner_backed_query_count": len(owner_results),
    }

    served_default_after = capture_served_default()
    default_switches = 0 if served_default_after == served_default_before else 1

    resource_bounds = {
        "p95_latency_ms_limit": 10000.0,
        "mean_tokens_limit": 10000.0,
        "p95_latency_ms_measured": shad_summary["latency_ms_p95"],
        "mean_tokens_measured": _mean([float(q["shadow"]["token_cost"]) for q in query_results]),
    }
    resource_bounds_pass = bool(
        resource_bounds["p95_latency_ms_measured"] <= resource_bounds["p95_latency_ms_limit"]
        and resource_bounds["mean_tokens_measured"] <= resource_bounds["mean_tokens_limit"]
    )

    non_regression = {
        "recall_at_5_pass": shad_summary["recall_at_5"] >= leg_summary["recall_at_5"],
        "mrr_pass": shad_summary["mrr"] >= leg_summary["mrr"],
        "map_pass": shad_summary["map"] >= leg_summary["map"],
        "ndcg_at_10_pass": shad_summary["ndcg_at_10"] >= leg_summary["ndcg_at_10"],
    }

    hard_invariants = {
        "authority_order_violations": auth_order_metric,
        "authority_order_violations_pass": auth_order_metric["pass"],
        "authority_winner_missing": auth_winner_missing_metric,
        "authority_winner_missing_pass": auth_winner_missing_metric["pass"],
        "authority_provenance_failures": auth_provenance_metric,
        "authority_provenance_failures_pass": auth_provenance_metric["pass"],
        "authority_outranked_by_relevance": auth_outranked_metric,
        "authority_outranked_by_relevance_pass": auth_outranked_metric["pass"],
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
        "default_switches": default_switches,
        "default_switches_pass": default_switches == 0,
        "resource_bounds_pass": resource_bounds_pass,
        "non_regression_pass": all(non_regression.values()),
    }
    all_pass = all(v is True for k, v in hard_invariants.items() if k.endswith("_pass"))
    quality_pass = bool(
        shad_summary["recall_at_5"] >= 0.70
        and shad_summary["mrr"] >= 0.50
        and shad_summary["ndcg_at_10"] >= 0.60
    )

    with (eval_corpus / "manifest.json").open("r", encoding="utf-8") as f:
        corpus_manifest = json.load(f)

    return {
        "benchmark_metadata": {
            "schema_version": "power.retrieval-benchmark-r5.v1",
            "runner": "benchmark_phase5e_r5",
            "runner_sha256": runner_sha,
            "fixture_manifest_path": str(manifest_path),
            "fixture_manifest_sha256": manifest_sha,
            "setup_state_digest": setup_state_digest,
            "setup_payload_digest": manifest.get("setup_payload_digest", ""),
            "source_corpus_digest": manifest.get("source_corpus_digest", ""),
            "budget_class": normalized_budget,
            "timestamp": datetime.now(UTC).isoformat(),
            "split": split,
            "eval_corpus_version": expected_revision,
            "query_count": len(query_results),
            "owner_backed_query_count": len(owner_results),
            "platform": platform.platform(),
            "python_version": sys.version,
            "all_hard_invariants_pass": all_pass,
            "quality_thresholds_pass": quality_pass,
            "corpus_manifest_digest": hashlib.sha256(
                json.dumps(corpus_manifest, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
        "fixture_receipts": receipts,
        "summary": {
            "legacy": leg_summary,
            "shadow": shad_summary,
            "non_regression": non_regression,
            "resource_bounds": resource_bounds,
        },
        "hard_invariants": hard_invariants,
        "security_discriminator": discriminator_checks,
        "queries": query_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-corpus", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--vault-dir", type=Path)
    parser.add_argument(
        "--fixture-manifest",
        type=Path,
        default=Path("artifacts/project-state/phase-5e/phase5e_runtime_fixture_manifest_r5.json"),
    )
    parser.add_argument("--expected-revision", type=str, default="v1.1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--budget-class", choices=("FAST", "BALANCED", "DEEP"), default="FAST")
    args = parser.parse_args(argv)

    eval_corpus = args.eval_corpus.resolve()
    manifest_path = args.fixture_manifest.resolve()
    if args.vault_dir:
        vault_dir = args.vault_dir.resolve()
        vault_dir.mkdir(parents=True, exist_ok=True)
        results = run_benchmark_r5(
            eval_corpus=eval_corpus,
            split=args.split,
            vault_dir=vault_dir,
            manifest_path=manifest_path,
            expected_revision=args.expected_revision,
            budget_class=args.budget_class,
        )
    else:
        tmp_obj = tempfile.TemporaryDirectory()
        try:
            vault_dir = Path(tmp_obj.name) / "r5_vault"
            vault_dir.mkdir(parents=True, exist_ok=True)
            results = run_benchmark_r5(
                eval_corpus=eval_corpus,
                split=args.split,
                vault_dir=vault_dir,
                manifest_path=manifest_path,
                expected_revision=args.expected_revision,
                budget_class=args.budget_class,
            )
        finally:
            with contextlib.suppress(Exception):
                tmp_obj.cleanup()

    if args.output:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"R5 results written to {out}")

    shadow_summary = results["summary"]["shadow"]
    safe_shadow = {
        "recall_at_5": float(shadow_summary["recall_at_5"]),
        "mrr": float(shadow_summary["mrr"]),
        "ndcg_at_10": float(shadow_summary["ndcg_at_10"]),
        "map": float(shadow_summary["map"]),
        "authority_winner_missing": int(shadow_summary["authority_winner_missing"]),
        "authority_provenance_failures": int(shadow_summary["authority_provenance_failures"]),
        "authority_outranked_by_relevance": int(shadow_summary["authority_outranked_by_relevance"]),
        "authority_violations": int(shadow_summary["authority_violations"]),
    }
    print("Hard Invariants Pass:", results["benchmark_metadata"]["all_hard_invariants_pass"])
    print("Quality Thresholds Pass:", results["benchmark_metadata"]["quality_thresholds_pass"])
    print(json.dumps(safe_shadow, indent=2, sort_keys=True))
    if not results["benchmark_metadata"]["all_hard_invariants_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
