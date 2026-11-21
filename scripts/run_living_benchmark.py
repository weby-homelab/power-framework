#!/usr/bin/env python3
"""POWER 3.8 Phase 5E - Living Retrieval Regression Benchmark.

Evaluates production ApplicationService.compile_context across FAST (lexical)
and BALANCED (Stage 3 mode="semantic" dense) profiles on one maintainable living
regression dataset (`benchmarks/power38/living_regression/`).

Supports two embedder modes:
  - hermetic (default): deterministic 1024-dim multilingual concept-lexicon
    embedder with zero network calls or external model weights.
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
import sqlite3
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
from power_framework.core.constants import DENSE_INDEX_SCHEMA_VERSION  # noqa: E402
from power_framework.core.decision_service import DecisionService  # noqa: E402
from power_framework.core.generation_index import (  # noqa: E402
    _file_identity,
    _state_db_path,
    invalidate_active_generation_cache,
    sync_vault_atomically,
)
from power_framework.core.project_models import AppendCommand  # noqa: E402
from power_framework.core.project_store import ProjectEventStore  # noqa: E402
from power_framework.core.search_scope import ResolvedSearchScope  # noqa: E402
from power_framework.core.searcher import (  # noqa: E402
    DEFAULT_SEARCH_MODE,
    _read_db_path,
    configured_embedding_identity,
)
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
    hits = sum(1 for item in retrieved[:k] if item in relevant)
    return hits / float(len(relevant))


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
    gains = [graded_relevance.get(item, 0.0) for item in retrieved[:k]]
    dcg = sum((2.0**g - 1.0) / math.log2(i + 2.0) for i, g in enumerate(gains))
    ideal = sorted(graded_relevance.values(), reverse=True)[:k]
    idcg = sum((2.0**g - 1.0) / math.log2(i + 2.0) for i, g in enumerate(ideal))
    return (dcg / idcg) if idcg > 0.0 else 1.0


class DeterministicMultilingualEmbedder:
    """Query-ID-blind multilingual vector embedder built from concept clusters + token hashes."""

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


def _populate_hermetic_dense_index(
    vault_dir: Path, embedder: DeterministicMultilingualEmbedder
) -> None:
    import numpy as np

    db_path = _read_db_path(vault_dir)
    if db_path is None:
        raise RuntimeError("Active search generation database missing after FTS sync")

    provider, model = configured_embedding_identity()
    with contextlib.closing(sqlite3.connect(db_path, timeout=30)) as conn:
        rows = conn.execute(
            "SELECT rel_path, title, description, content FROM fts_notes ORDER BY rel_path"
        ).fetchall()
        mtimes = dict(conn.execute("SELECT rel_path, mtime FROM file_metadata").fetchall())

        chunk_rows: list[tuple[str, str, bytes, str, float]] = []
        for idx, (rel_path, title, description, content) in enumerate(rows):
            full_text = f"{title}\n{description}\n{content}"
            vec = np.asarray(embedder.embed(full_text), dtype=np.float32)
            chunk_rows.append(
                (
                    f"living_c{idx}_{hashlib.sha256(str(rel_path).encode('utf-8')).hexdigest()[:8]}",
                    str(rel_path),
                    vec.tobytes(),
                    str(content),
                    float(mtimes.get(rel_path, 0.0)),
                )
            )

        conn.execute("DELETE FROM chunk_embeddings")
        conn.executemany(
            "INSERT INTO chunk_embeddings (chunk_id, rel_path, embedding, content, mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            chunk_rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO dense_index_manifest (manifest_key, manifest_value) VALUES (?, ?)",
            [
                ("schema_version", DENSE_INDEX_SCHEMA_VERSION),
                ("embedding_dimension", str(embedder.dim)),
                ("chunk_count", str(len(chunk_rows))),
                ("embedding_provider", provider),
                ("embedding_model", model),
            ],
        )
        conn.commit()

    new_sha, new_size = _file_identity(db_path)
    state_db = _state_db_path(vault_dir)
    with contextlib.closing(sqlite3.connect(state_db, timeout=30)) as state_conn:
        state_conn.execute(
            "UPDATE index_generations SET db_sha256 = ?, db_size = ?",
            (new_sha, new_size),
        )
        state_conn.commit()
    invalidate_active_generation_cache(vault_dir)


def build_living_vault(
    vault_dir: Path,
    dataset_dir: Path,
    *,
    embedder_mode: str = "hermetic",
    need_dense: bool = True,
) -> DeterministicMultilingualEmbedder | None:
    """Materialize a fresh OKF vault seeded with corpus notes, canonical stores, and indexes."""
    root = vault_dir.expanduser().resolve()
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

    sync_vault_atomically(root, sync_embeddings=False)
    if not need_dense:
        return None
    embedder = DeterministicMultilingualEmbedder(lexicon)
    _populate_hermetic_dense_index(root, embedder)
    return embedder


def _is_vault_contained(vault_root: Path, raw_id: str, source_refs: Sequence[str]) -> bool:
    scope = ResolvedSearchScope(include_archived=False, include_quarantine=False)
    for candidate in (raw_id, *source_refs):
        if not candidate:
            continue
        if candidate.startswith(("task:", "decision:", "project:")):
            continue
        p = Path(candidate)
        if p.is_absolute():
            try:
                if not p.resolve().is_relative_to(vault_root):
                    return False
            except OSError:
                return False
            continue
        try:
            resolved = (vault_root / p).resolve()
        except OSError:
            return False
        if not resolved.is_relative_to(vault_root):
            return False
        if not scope.is_path_in_scope(candidate):
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

        r5 = compute_recall_at_k(retrieved_ids, rel_set, 5)
        mrr = compute_reciprocal_rank(retrieved_ids, rel_set)
        ndcg10 = compute_ndcg(retrieved_ids, graded, 10)
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
            if not _is_vault_contained(vault_root, raw_id, refs):
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
        count = len(rows)
        if count == 0:
            return {"count": 0, "recall_at_5": 0.0, "mrr": 0.0, "ndcg_at_10": 0.0}
        return {
            "count": count,
            "recall_at_5": round(sum(float(r["recall_at_5"]) for r in rows) / count, 4),
            "mrr": round(sum(float(r["mrr"]) for r in rows) / count, 4),
            "ndcg_at_10": round(sum(float(r["ndcg_at_10"]) for r in rows) / count, 4),
        }

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
    """Build or reuse a living vault and evaluate requested budget profiles."""
    normalized_modes = [m.strip().upper() for m in modes if m.strip()]
    if not normalized_modes:
        raise ValueError("at least one retrieval mode must be requested")
    need_dense = any(m != "FAST" for m in normalized_modes)

    _canonical, _lexicon, queries = load_dataset(dataset_dir)

    with contextlib.ExitStack() as stack:
        scratch = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="power_living_")))
        stack.enter_context(patch.dict(os.environ, {"XDG_CACHE_HOME": str(scratch / "cache")}))
        os.environ.pop("POWER_SEARCH_DB", None)
        if vault_dir is None:
            active_vault = scratch / "vault"
        else:
            active_vault = Path(vault_dir).expanduser().resolve()

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

        mode_reports = {
            mode: _run_mode(active_vault, queries, budget_class=mode) for mode in normalized_modes
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
        if mode_name == "BALANCED":
            if summary["dense_used_count"] != report["query_count"]:
                failures.append(
                    f"BALANCED dense_used_count {summary['dense_used_count']} != {report['query_count']}"
                )
            if summary["degraded_count"] != 0:
                failures.append(f"BALANCED degraded_count {summary['degraded_count']} != 0")
            if summary["recall_at_5"] < 0.85:
                failures.append(f"BALANCED recall_at_5 below floor: {summary['recall_at_5']}")
            if summary["mrr"] < 0.80:
                failures.append(f"BALANCED mrr below floor: {summary['mrr']}")
            if summary["ndcg_at_10"] < 0.85:
                failures.append(f"BALANCED ndcg_at_10 below floor: {summary['ndcg_at_10']}")

    if "FAST" in modes and "BALANCED" in modes:
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
