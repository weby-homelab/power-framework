#!/usr/bin/env python3
"""POWER 3.8 Phase 5E - Living Retrieval Regression Benchmark.

Evaluates production ApplicationService.compile_context across FAST (lexical)
and BALANCED (Stage 3 mode="semantic" dense) profiles on one maintainable living
regression dataset (`benchmarks/power38/living_regression/`).

Supports two embedder modes:
  - hermetic (default): dataset-specific deterministic fixture for dense path
    and invariant checks, not an embedding quality evaluation.
  - real: local BGEM3OnnxManager via sync_vault_atomically(..., sync_embeddings=True)
    for host verification on S-Book (OMP_NUM_THREADS=4, POWER_EMBED_DEVICE=auto).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from power_framework.core.application import ApplicationService  # noqa: E402
from power_framework.core.decision_service import DecisionService  # noqa: E402
from power_framework.core.generation_index import sync_vault_atomically  # noqa: E402
from power_framework.core.project_models import AppendCommand  # noqa: E402
from power_framework.core.project_store import ProjectEventStore  # noqa: E402
from power_framework.core.search_scope import ResolvedSearchScope  # noqa: E402
from power_framework.core.searcher import DEFAULT_SEARCH_MODE  # noqa: E402
from power_framework.core.task_service import TaskService  # noqa: E402
from power_framework.core.vault_storage import existing_vault_cache_dir  # noqa: E402

DEFAULT_DATASET_DIR = _REPO_ROOT / "benchmarks" / "power38" / "living_regression"
_AUTHORITY_RANK = {
    "canonical": 0,
    "verified": 1,
    "curated": 2,
    "proposed": 3,
    "unverified": 4,
    "unknown": 5,
}
_CANONICAL_BASES = frozenset({"canonical_ledger", "verified_projection", "curated_note"})
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_ID_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_LEAK_RE = re.compile(
    r"(?:"
    r"\bgh[po]_[A-Za-z0-9]{20,}"
    r"|\bglpat-[A-Za-z0-9\-_]{20,}"
    r"|-----BEGIN\s+(?:RSA|PGP|OPENSSH|EC)\s+PRIVATE\s+KEY-----"
    r")"
)
_INJECTION_TRAP_STEM = "prompt_injection_trap"
_CLUSTER_STRIDE = 16
_CLUSTER_DIMS = 512


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(root: Path, *, sqlite_cache: bool = False) -> dict[str, str]:
    """Compute a deterministic SHA-256 manifest of all files inside root."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if sqlite_cache and (
            (path.name.endswith(".db-shm") and path.with_suffix(".db").is_file())
            or (
                path.name.endswith(".db-wal")
                and path.with_suffix(".db").is_file()
                and path.stat().st_size == 0
            )
        ):
            # Read-only SQLite connections can initialize SHM and an empty WAL.
            # Keep hashing database files and any WAL that contains data.
            continue
        hashes[path.relative_to(root).as_posix()] = _sha256_file(path)
    return hashes


def _hash_benchmark_storage(
    vault_root: Path, cache_root: Path
) -> tuple[dict[str, str], dict[str, str]]:
    return _hash_tree(vault_root), _hash_tree(cache_root, sqlite_cache=True)


def compute_recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Recall@K; vacuously 1.0 when relevant set is intentionally empty."""
    if not relevant:
        return 1.0
    return len(relevant.intersection(retrieved[:k])) / float(len(relevant))


def compute_reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    """Reciprocal Rank; vacuously 1.0 when relevant set is intentionally empty."""
    if not relevant:
        return 1.0
    for idx, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / float(idx)
    return 0.0


def compute_ndcg(retrieved: Sequence[str], graded_relevance: dict[str, float], k: int) -> float:
    """Normalized Discounted Cumulative Gain at rank K."""
    if not graded_relevance:
        return 1.0
    seen: set[str] = set()
    gains = []
    for item in retrieved[:k]:
        gains.append(0.0 if item in seen else graded_relevance.get(item, 0.0))
        seen.add(item)
    dcg = sum((2.0**g - 1.0) / math.log2(i + 2.0) for i, g in enumerate(gains))
    ideal = sorted(graded_relevance.values(), reverse=True)[:k]
    idcg = sum((2.0**g - 1.0) / math.log2(i + 2.0) for i, g in enumerate(ideal))
    return (dcg / idcg) if idcg > 0.0 else 1.0


class DeterministicMultilingualEmbedder:
    """Dataset-specific multilingual smoke fixture, independent of query IDs."""

    model_name = "phase5e-hermetic"

    def __init__(self, lexicon: dict[str, Any]) -> None:
        self.dim = int(lexicon.get("dimension", 1024))
        raw_clusters = lexicon.get("clusters", {})
        self.clusters: list[tuple[str, tuple[str, ...]]] = [
            (str(name), tuple(str(term).casefold() for term in terms))
            for name, terms in sorted(raw_clusters.items())
        ]
        if len(self.clusters) * _CLUSTER_STRIDE > _CLUSTER_DIMS:
            raise ValueError("cluster dimension budget exceeded")

    def embed(self, text: str) -> list[float]:
        """Encode plain text into a unit-normalized dense float vector."""
        import numpy as np

        vec = np.zeros(self.dim, dtype=np.float32)
        lowered = (text or "").casefold()
        tokens = [tok for tok in _WORD_RE.findall(lowered) if len(tok) >= 3]

        for idx, (_name, terms) in enumerate(self.clusters):
            hits = sum(1 for term in terms if term in lowered)
            if hits > 0:
                weight = 3.0 * float(min(hits, 4))
                start = idx * _CLUSTER_STRIDE
                vec[start : start + _CLUSTER_STRIDE] += weight

        hash_span = max(1, self.dim - _CLUSTER_DIMS)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            slot = _CLUSTER_DIMS + (int.from_bytes(digest[:4], "little") % hash_span)
            vec[slot] += 1.0

        norm = float(np.linalg.norm(vec))
        if norm == 0.0:
            vec[0] = 1.0
        else:
            vec /= norm
        return [float(x) for x in vec.tolist()]

    def dimension(self) -> int:
        return self.dim

    def embed_batch(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        del batch_size
        return [self.embed(text) for text in texts]


def load_dataset(dataset_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Load canonical records, concept lexicon, and queries from dataset_dir."""
    root = dataset_dir.resolve()
    canonical = json.loads((root / "canonical_records.json").read_text(encoding="utf-8"))
    lexicon = json.loads((root / "concept_lexicon.json").read_text(encoding="utf-8"))
    queries: list[dict[str, Any]] = []
    for raw_line in (root / "queries.jsonl").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line:
            queries.append(json.loads(line))
    return canonical, lexicon, queries


def _seed_canonical_records(vault_dir: Path, canonical: dict[str, Any]) -> None:
    task_svc = TaskService(vault_dir)
    for task in canonical.get("tasks", []):
        task_svc.create_task(
            task_id=str(task["task_id"]),
            title=str(task["title"]),
            objective=str(task.get("objective", "")),
            owner=str(task.get("owner", "maintainer")),
            state=task.get("state", "active"),
            priority=task.get("priority", "normal"),
            next_action=str(task.get("next_action", "inspect")),
        )

    decision_svc = DecisionService(vault_dir, task_service=task_svc)
    for dec in canonical.get("decisions", []):
        decision_svc.create_decision(
            decision_id=str(dec["decision_id"]),
            task_id=str(dec["task_id"]),
            title=str(dec["title"]),
            requested_by=str(dec["requested_by"]),
            description=str(dec.get("description", "")),
            risk_level=str(dec.get("risk_level", "medium")),
        )

    for proj in canonical.get("projects", []):
        pid = str(proj["project_id"])
        ProjectEventStore(pid, vault_dir)._append_governed(
            AppendCommand(
                project_id=pid,
                event_type="project.created",
                payload={"name": str(proj["name"]), "owner": str(proj.get("owner", "maintainer"))},
                actor="user:maintainer",
                source="pse_governance",
            )
        )


def _hermetic_identity(embedder: DeterministicMultilingualEmbedder) -> tuple[str, str]:
    return type(embedder).__name__, embedder.model_name


def build_living_vault(
    vault_dir: Path,
    dataset_dir: Path,
    *,
    embedder_mode: str = "hermetic",
    need_dense: bool = True,
) -> DeterministicMultilingualEmbedder | None:
    """Materialize a fresh OKF vault. Never reuse an existing destination."""
    destination = vault_dir.expanduser()
    destination.mkdir(parents=True)
    root = destination.resolve()
    for folder in (
        "01_Projects",
        "02_Areas",
        "03_Resources",
        "04_Archive",
        "05_Templates",
        "06_Daily_Logs",
        ".power",
    ):
        (root / folder).mkdir(parents=True, exist_ok=True)

    (root / "05_Templates" / "project.md").write_text(
        "---\ntype: Project\ntitle: Template\n---\n# Template\n",
        encoding="utf-8",
    )
    domains_yaml = """version: 1
domains:
  - name: projects
    path: 01_Projects
    template: 05_Templates/project.md
    search_priority: [fts, vector]
  - name: areas
    path: 02_Areas
    template: 05_Templates/project.md
    search_priority: [fts, vector]
  - name: resources
    path: 03_Resources
    template: 05_Templates/project.md
    search_priority: [fts, vector]
  - name: daily
    path: 06_Daily_Logs
    template: 05_Templates/project.md
    search_priority: [fts, vector]
"""
    (root / ".power" / "domains.yaml").write_text(domains_yaml, encoding="utf-8")

    corpus_root = dataset_dir.resolve() / "corpus"
    for src in sorted(corpus_root.rglob("*.md")):
        rel = src.relative_to(corpus_root)
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    canonical, lexicon, _queries = load_dataset(dataset_dir)
    _seed_canonical_records(root, canonical)

    if embedder_mode == "real":
        sync_vault_atomically(root, sync_embeddings=need_dense)
        return None
    if embedder_mode != "hermetic":
        raise ValueError(f"Unsupported embedder_mode: {embedder_mode}")

    if not need_dense:
        sync_vault_atomically(root, sync_embeddings=False)
        return None
    embedder = DeterministicMultilingualEmbedder(lexicon)
    with (
        patch("power_framework.core.index_sync._get_embedding_manager", return_value=embedder),
        patch(
            "power_framework.core.index_sync._configured_embedding_identity",
            return_value=_hermetic_identity(embedder),
        ),
    ):
        sync_vault_atomically(root, sync_embeddings=True)
    return embedder


def _is_vault_contained(
    vault_root: Path,
    raw_id: str,
    source_refs: Sequence[str],
    canonical_ids: frozenset[str] = frozenset(),
) -> bool:
    scope = ResolvedSearchScope(include_archived=False, include_quarantine=False)
    paths = source_refs if raw_id in canonical_ids else (raw_id, *source_refs)
    for candidate in paths:
        if not candidate or _ID_SCHEME_RE.match(candidate):
            return False
        p = Path(candidate)
        try:
            relative = (vault_root / p).resolve().relative_to(vault_root)
        except (OSError, ValueError, RuntimeError):
            return False
        if not scope.is_path_in_scope(relative.as_posix()):
            return False
    return True


def _has_canonical_provenance(item: dict[str, Any]) -> bool:
    auth = str(item.get("authority", "")).casefold()
    prov = item.get("provenance") or {}
    basis = str(prov.get("authority_basis", "")).casefold() if isinstance(prov, dict) else ""
    source_type = str(item.get("source_type", "")).casefold()
    return (
        auth == "canonical"
        and basis in _CANONICAL_BASES
        and source_type in {"canonical_task", "canonical_decision", "canonical_project"}
    )


def _capture_default_boundary() -> dict[str, str]:
    import inspect

    sig = inspect.signature(ApplicationService.retrieve)
    return {
        "DEFAULT_SEARCH_MODE": str(DEFAULT_SEARCH_MODE),
        "retrieve_default_mode": str(sig.parameters["mode"].default),
    }


def _run_mode(
    vault_dir: Path,
    queries: list[dict[str, Any]],
    *,
    budget_class: str,
    canonical_ids: frozenset[str],
) -> dict[str, Any]:
    app = ApplicationService(vault_dir)
    vault_root = vault_dir.resolve()
    cache_root = existing_vault_cache_dir(vault_root)
    if cache_root is None or not cache_root.is_dir():
        raise RuntimeError("benchmark vault cache is missing")
    baseline_storage = _hash_benchmark_storage(vault_root, cache_root)
    default_before = _capture_default_boundary()

    query_side_writes = 0
    scope_escapes = 0
    secret_leakages = 0
    injection_escalations = 0
    authority_order_violations = 0
    authority_outranked = 0
    authority_provenance_failures = 0
    determinism_mismatches = 0
    exclusion_leaks = 0
    dense_used_count = 0
    degraded_count = 0

    per_query: list[dict[str, Any]] = []
    by_group_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_lang_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for q in queries:
        qid = str(q["query_id"])
        intent = str(q["intent"])
        hints = list(q.get("domain_hints") or [])

        t0 = time.perf_counter()
        env = app.compile_context(
            query=str(q["query"]),
            intent=intent,
            budget_class=budget_class,
            domain_hints=hints or None,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        first_read_wrote = _hash_benchmark_storage(vault_root, cache_root) != baseline_storage

        data: dict[str, Any] = env.data
        raw_items = data.get("items")
        items: list[dict[str, Any]] = list(raw_items) if isinstance(raw_items, list) else []
        retrieved_ids = [str(it.get("source_id", "")) for it in items]
        authorities = [str(it.get("authority", "unknown")).casefold() for it in items]

        # Determinism check (repeat read on same query)
        env2 = app.compile_context(
            query=str(q["query"]),
            intent=intent,
            budget_class=budget_class,
            domain_hints=hints or None,
        )
        raw_items2 = env2.data.get("items")
        items2: list[dict[str, Any]] = list(raw_items2) if isinstance(raw_items2, list) else []
        if json.dumps(items, sort_keys=True) != json.dumps(items2, sort_keys=True):
            determinism_mismatches += 1

        if first_read_wrote or _hash_benchmark_storage(vault_root, cache_root) != baseline_storage:
            query_side_writes += 1

        raw_budget = data.get("budget")
        budget_info: dict[str, Any] = raw_budget if isinstance(raw_budget, dict) else {}
        dense_used = bool(budget_info.get("dense_used", False))
        if dense_used:
            dense_used_count += 1
        if str(data.get("retrieval_status", "")) == "degraded":
            degraded_count += 1

        rel_set = {str(x) for x in q.get("expected_relevant", [])}
        graded = {str(k): float(v) for k, v in (q.get("graded_relevance") or {}).items()}
        excl_set = {str(x) for x in q.get("expected_exclusions", [])}

        r5 = compute_recall_at_k(retrieved_ids, rel_set, 5) if rel_set else None
        mrr = compute_reciprocal_rank(retrieved_ids, rel_set) if rel_set else None
        ndcg10 = compute_ndcg(retrieved_ids, graded, 10) if graded else None
        q_excl_leaks = sum(1 for sid in retrieved_ids[:10] if sid in excl_set)
        exclusion_leaks += q_excl_leaks

        # Authority ordering inside returned ContextPack (raw/unverified must not outrank canonical/verified)
        seen_unverified = False
        for auth in authorities:
            lvl = _AUTHORITY_RANK.get(auth, 5)
            if lvl >= 4:
                seen_unverified = True
            elif seen_unverified and lvl <= 1:
                authority_order_violations += 1

        # Ground-truth authority winner check
        winner = q.get("expected_authority_winner")
        if winner:
            winner_str = str(winner)
            if winner_str not in retrieved_ids:
                authority_outranked += 1
                authority_provenance_failures += 1
            else:
                widx = retrieved_ids.index(winner_str)
                if not _has_canonical_provenance(items[widx]):
                    authority_provenance_failures += 1
                    authority_outranked += 1
                elif any(sid in excl_set for sid in retrieved_ids[:widx]):
                    authority_outranked += 1

        for it in items:
            raw_id = str(it.get("source_id", ""))
            prov = it.get("provenance") or {}
            refs = (
                [str(r) for r in prov.get("source_refs", [])]
                if isinstance(prov, dict) and isinstance(prov.get("source_refs"), list)
                else []
            )
            if not _is_vault_contained(vault_root, raw_id, refs, canonical_ids):
                scope_escapes += 1
            excerpt = str(it.get("excerpt", ""))
            if _LEAK_RE.search(excerpt):
                secret_leakages += 1
            if _INJECTION_TRAP_STEM in raw_id and str(it.get("authority", "")).casefold() in {
                "canonical",
                "verified",
                "curated",
            }:
                injection_escalations += 1

        group = str(q.get("group", "core"))
        language = str(q.get("language", "EN"))
        row = {
            "query_id": qid,
            "group": group,
            "language": language,
            "recall_at_5": r5,
            "mrr": mrr,
            "ndcg_at_10": ndcg10,
            "latency_ms": round(latency_ms, 2),
            "dense_used": dense_used,
            "retrieval_status": str(data.get("retrieval_status", "")),
            "exclusion_leaks": q_excl_leaks,
            "retrieved": retrieved_ids[:5],
        }
        per_query.append(row)
        by_group_rows[group].append(row)
        by_lang_rows[language].append(row)

    default_switches = 0 if _capture_default_boundary() == default_before else 1

    def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {"count": len(rows), "scored_counts": {}}
        for key in ("recall_at_5", "mrr", "ndcg_at_10"):
            scores = [float(row[key]) for row in rows if row[key] is not None]
            result[key] = round(sum(scores) / len(scores), 4) if scores else 0.0
            result["scored_counts"][key] = len(scores)
        return result

    overall = _agg(per_query)
    overall["mean_latency_ms"] = (
        round(sum(float(r["latency_ms"]) for r in per_query) / len(per_query), 2)
        if per_query
        else 0.0
    )
    overall["dense_used_count"] = dense_used_count
    overall["degraded_count"] = degraded_count
    overall["exclusion_leaks"] = exclusion_leaks

    invariants = {
        "query_side_writes": query_side_writes,
        "scope_escape": scope_escapes,
        "secret_leakage": secret_leakages,
        "prompt_injection_authority_escalation": injection_escalations,
        "authority_order_violations": authority_order_violations,
        "authority_outranked": authority_outranked,
        "authority_provenance_failures": authority_provenance_failures,
        "determinism_mismatches": determinism_mismatches,
        "default_switches": default_switches,
        "exclusion_leaks": exclusion_leaks,
    }

    return {
        "budget_class": budget_class,
        "summary": overall,
        "by_group": {k: _agg(v) for k, v in sorted(by_group_rows.items())},
        "by_language": {k: _agg(v) for k, v in sorted(by_lang_rows.items())},
        "invariants": invariants,
        "all_invariants_zero": all(val == 0 for val in invariants.values()),
        "queries": per_query,
    }


def run_living_benchmark(
    dataset_dir: Path = DEFAULT_DATASET_DIR,
    *,
    modes: Sequence[str] = ("FAST", "BALANCED"),
    embedder_mode: str = "hermetic",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    """Build a disposable or explicitly new vault and evaluate requested budget profiles."""
    normalized_modes = [m.strip().upper() for m in modes if m.strip()]
    if not normalized_modes:
        raise ValueError("at least one retrieval mode must be requested")
    need_dense = any(m != "FAST" for m in normalized_modes)

    canonical, _lexicon, queries = load_dataset(dataset_dir)
    canonical_ids = frozenset(
        f"{kind}:{entry[f'{kind}_id']}"
        for kind in ("task", "decision", "project")
        for entry in canonical.get(f"{kind}s", [])
    )

    with contextlib.ExitStack() as stack:
        scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="power_living_")))
        # patch.dict restores the caller's entire environment, including the removed override.
        stack.enter_context(patch.dict(os.environ, {"XDG_CACHE_HOME": str(scratch / "cache")}))
        os.environ.pop("POWER_SEARCH_DB", None)
        active_vault = scratch / "vault" if vault_dir is None else vault_dir.expanduser().absolute()

        embedder = build_living_vault(
            active_vault,
            dataset_dir,
            embedder_mode=embedder_mode,
            need_dense=need_dense,
        )

        if embedder_mode == "hermetic" and need_dense:
            if embedder is None:
                raise RuntimeError("hermetic embedder failed to initialize")
            stack.enter_context(
                patch(
                    "power_framework.core.retrieval_planner.dense_embedding_ready",
                    return_value=(True, "ready"),
                )
            )
            stack.enter_context(
                patch(
                    "power_framework.core.searcher.get_embedding_manager",
                    return_value=embedder,
                )
            )
            stack.enter_context(
                patch(
                    "power_framework.core.searcher.configured_embedding_identity",
                    return_value=_hermetic_identity(embedder),
                )
            )

        mode_reports = {
            mode: _run_mode(active_vault, queries, budget_class=mode, canonical_ids=canonical_ids)
            for mode in normalized_modes
        }

    return {
        "schema_version": "power.living-benchmark.v1",
        "dataset_dir": str(dataset_dir.resolve()),
        "embedder_mode": embedder_mode,
        "query_count": len(queries),
        "modes": mode_reports,
    }


def _gates_pass(report: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    modes: dict[str, Any] = report.get("modes", {})
    real_quality = report["embedder_mode"] == "real"
    for mode_name, mode_data in modes.items():
        if not mode_data.get("all_invariants_zero"):
            failures.append(f"{mode_name}: invariant violation {mode_data.get('invariants')}")
        summary = mode_data["summary"]
        if mode_name == "FAST":
            if summary["dense_used_count"] != 0:
                failures.append(f"FAST used dense unexpectedly: {summary['dense_used_count']}")
            if summary["recall_at_5"] < 0.55:
                failures.append(f"FAST recall_at_5 below floor: {summary['recall_at_5']}")
            if summary["mrr"] < 0.50:
                failures.append(f"FAST mrr below floor: {summary['mrr']}")
            if summary["ndcg_at_10"] < 0.55:
                failures.append(f"FAST ndcg_at_10 below floor: {summary['ndcg_at_10']}")
            core_recall = mode_data["by_group"].get("core", {}).get("recall_at_5", 0.0)
            if core_recall < 0.80:
                failures.append(f"FAST core recall_at_5 below floor: {core_recall}")
        if mode_name == "BALANCED":
            if summary["dense_used_count"] != report["query_count"]:
                failures.append(
                    f"BALANCED dense_used_count {summary['dense_used_count']} != {report['query_count']}"
                )
            if summary["degraded_count"] != 0:
                failures.append(f"BALANCED degraded_count {summary['degraded_count']} != 0")
            if real_quality and summary["recall_at_5"] < 0.85:
                failures.append(f"BALANCED recall_at_5 below floor: {summary['recall_at_5']}")
            if real_quality and summary["mrr"] < 0.80:
                failures.append(f"BALANCED mrr below floor: {summary['mrr']}")
            if real_quality and summary["ndcg_at_10"] < 0.85:
                failures.append(f"BALANCED ndcg_at_10 below floor: {summary['ndcg_at_10']}")
            if real_quality:
                semantic_recall = (
                    mode_data["by_group"].get("semantic_paraphrase", {}).get("recall_at_5", 0.0)
                )
                if semantic_recall < 0.85:
                    failures.append(
                        f"BALANCED semantic_paraphrase recall_at_5 below floor: {semantic_recall}"
                    )

    if real_quality and "FAST" in modes and "BALANCED" in modes:
        fast_sem = modes["FAST"]["by_group"].get("semantic_paraphrase", {}).get("recall_at_5", 0.0)
        bal_sem = (
            modes["BALANCED"]["by_group"].get("semantic_paraphrase", {}).get("recall_at_5", 0.0)
        )
        if bal_sem <= fast_sem:
            failures.append(
                f"BALANCED semantic_paraphrase recall ({bal_sem}) did not beat FAST ({fast_sem})"
            )
    return (not failures), failures


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the living retrieval regression benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Path to living regression dataset directory.",
    )
    parser.add_argument(
        "--modes",
        default="FAST,BALANCED",
        help="Comma-separated budget modes to run (default: FAST,BALANCED).",
    )
    parser.add_argument(
        "--embedder",
        choices=("hermetic", "real"),
        default="hermetic",
        help="Dense embedder backend (default: hermetic).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write full JSON report.",
    )
    parser.add_argument(
        "--enforce-gates",
        action="store_true",
        help="Exit non-zero if any safety invariant or quality floor fails.",
    )
    args = parser.parse_args(argv)

    modes = [part.strip().upper() for part in str(args.modes).split(",") if part.strip()]
    report = run_living_benchmark(
        args.dataset,
        modes=modes,
        embedder_mode=args.embedder,
    )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"POWER Living Benchmark (embedder={report['embedder_mode']}, "
        f"queries={report['query_count']})"
    )
    for mode_name, mdata in report["modes"].items():
        s = mdata["summary"]
        sem_r5 = mdata["by_group"].get("semantic_paraphrase", {}).get("recall_at_5", 0.0)
        core_r5 = mdata["by_group"].get("core", {}).get("recall_at_5", 0.0)
        print(
            f"  {mode_name:8s} | R@5={s['recall_at_5']:.4f} | MRR={s['mrr']:.4f} | "
            f"nDCG@10={s['ndcg_at_10']:.4f} | core_R@5={core_r5:.4f} | "
            f"sem_R@5={sem_r5:.4f} | dense={s['dense_used_count']}/{report['query_count']} | "
            f"degraded={s['degraded_count']} | inv_zero={mdata['all_invariants_zero']} | "
            f"lat={s['mean_latency_ms']:.2f}ms"
        )

    if args.enforce_gates:
        ok, failures = _gates_pass(report)
        if not ok:
            for item in failures:
                print(f"GATE FAIL: {item}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
