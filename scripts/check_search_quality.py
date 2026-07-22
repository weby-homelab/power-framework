#!/usr/bin/env python3
"""POWER 3.0 Phase 2 — Deterministic Search-Quality Evaluation Harness.

This script builds a deterministic ground-truth (GT) relevance set from a vault
using grep-style content validation (NO LLM / NO API), runs the canonical
``search_vault`` reranked pipeline over a curated query set, and scores the run.

Legacy diagnostic metric: normalized discounted lexical gain@5 (see
``power_framework.core.metrics.discounted_lexical_gain``), which captures a
LLM RAG reader rather than just graded relevance. SECONDARY: ndcg@5 / recall@5 /
mrr@5 (via ``ranx``).

The GT rule mirrors the project convention "each GT doc MUST contain the query
terms": a markdown file is GT-relevant for a query iff its (lowercased,
tokenized) CONTENT contains ALL non-stopword query terms (AND semantics). This
makes the qrels fully reproducible and API-free.

Usage:
    python scripts/check_search_quality.py \
        --vault /root/gemma/brain --mode reranked --gate 0.50 --udcg-gate 0.45

Exit code 0 = gate passed (ndcg@5 >= gate AND udcg@5 >= udcg_gate), 1 = failed.

This harness ONLY creates new files (the qrels cache under .cache/); it never
modifies any source under src/power_framework/.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache"
QRELS_CACHE = CACHE_DIR / "search_qrels.json"

# Ukrainian + English stopwords. Kept minimal and deterministic.
_STOPWORDS: set[str] = {
    # english
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "by",
    "at",
    "as",
    "it",
    "this",
    "that",
    "from",
    "how",
    "what",
    "which",
    "who",
    "why",
    "when",
    "where",
    "can",
    "do",
    "does",
    "did",
    "has",
    "have",
    "had",
    "my",
    "our",
    "your",
    "their",
    "me",
    "us",
    "you",
    "they",
    "he",
    "she",
    "we",
    "i",
    "not",
    "no",
    "yes",
    "about",
    "into",
    "than",
    "then",
    "so",
    "if",
    "but",
    "all",
    "any",
    "some",
    "more",
    "most",
    "very",
    "just",
    "only",
    "also",
    "out",
    "up",
    "down",
    "over",
    "under",
    "between",
    "both",
    "each",
    "its",
    "there",
    "here",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "must",
    "using",
    "use",
    "used",
    "via",
    "per",
    "vs",
    "etc",
    # ukrainian
    "та",
    "й",
    "в",
    "у",
    "на",
    "з",
    "із",
    "до",
    "для",
    "про",
    "по",
    "за",
    "від",
    "о",
    "об",
    "як",
    "що",
    "це",
    "той",
    "там",
    "тут",
    "ми",
    "ви",
    "вони",
    "він",
    "вона",
    "воно",
    "не",
    "ні",
    "так",
    "чи",
    "але",
    "бо",
    "же",
    "лише",
    "тільки",
    "ще",
    "вже",
    "коли",
    "де",
    "чому",
    "який",
    "яка",
    "яке",
    "які",
    "хто",
    "щоб",
    "при",
    "під",
    "над",
    "через",
    "після",
    "перед",
    "без",
    "к",
    "заз",
    "цього",
    "того",
    "свій",
    "свою",
    "своє",
    "свої",
    "цих",
    "цим",
    "цій",
    "їх",
    "її",
    "наш",
    "наша",
    "наше",
    "ваш",
    "ваша",
    "мій",
    "моя",
    "моє",
    "я",
    "ти",
    "мене",
    "тебе",
    "нас",
    "вас",
    "йому",
    "їй",
    "ним",
    "нею",
    "цьому",
    "один",
    "одна",
    "одне",
    "два",
    "три",
    "бути",
    "є",
    "був",
    "була",
    "було",
    "були",
    "то",
    "такий",
    "така",
    "таке",
    "такі",
    "цей",
    "ця",
    "ці",
    "с",
    "п",
    "би",
    "б",
    "наче",
    "мов",
    "нібито",
    "просто",
    "дуже",
    "трохи",
    "майже",
    "взагалі",
    "всього",
    "всі",
    "всіх",
    "всієї",
    "всю",
}


# Curated query set: realistic search intents over the Weby Homelab brain vault.
# Mix of Ukrainian + English, covering power / safety / infra / knowledge-base.
# Each query is chosen so the GT (AND of non-stopword content terms) yields a
# meaningful number of relevant docs in /root/gemma/brain, making ndcg@5 a
# sensitive, fair quality signal rather than an all-empty or all-trivial qrels.
DEFAULT_QUERIES: list[str] = [
    # English — power / safety / infra / knowledge-base
    "power safety",
    "server inventory",
    "proxmox cluster",
    "gpg signing",
    "adguard dns",
    "docker compose",
    "obsidian vault",
    "knowledge base",
    "flash monitor kyiv",
    "tailscale vpn",
    "second brain",
    "git commit gpg",
    "adguard home",
    "reranker search",
    # Ukrainian — power / safety / infra / kb
    "резервне копіювання",
    "мережа tailscale",
]


def _ensure_ranx() -> Any:
    """Import ranx, installing it if missing. Returns the ranx module."""
    try:
        import ranx  # type: ignore

        return ranx
    except ModuleNotFoundError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "ranx", "--break-system-packages"]
        )
        import ranx  # type: ignore

        return ranx


def _tokenize_query(query: str) -> list[str]:
    """Tokenize a query into lowercase non-stopword content terms."""
    raw = re.findall(r"[a-z0-9а-яєіїґ']+", query.lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


def _iter_md_files(vault: Path) -> list[Path]:
    """Return all .md files under vault (excluding hidden dirs)."""
    out: list[Path] = []
    for p in vault.rglob("*.md"):
        parts = set(p.relative_to(vault).parts)
        if parts & {".git", ".cache", "node_modules", ".trash"}:
            continue
        out.append(p)
    return out


def _rel(p: Path, vault: Path) -> str:
    return str(p.relative_to(vault))


def build_qrels(
    vault: Path,
    queries: list[str] | None = None,
    overrides: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, int]]:
    """Build deterministic GT qrels: query -> {rel_doc: 1}.

    A doc is GT-relevant for a query iff its content contains ALL non-stopword
    query terms (AND). ``overrides`` map query -> explicit relevant doc rel_paths.
    """
    overrides = overrides or {}
    queries = queries if queries is not None else DEFAULT_QUERIES
    vault = Path(vault).resolve()
    files = _iter_md_files(vault)

    # Pre-load content for every md file once.
    contents: dict[str, str] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        contents[_rel(f, vault)] = text

    qrels: dict[str, dict[str, int]] = {}
    for q in queries:
        if overrides.get(q):
            qrels[q] = dict.fromkeys(overrides[q], 1)
            continue
        terms = _tokenize_query(q)
        if not terms:
            qrels[q] = {}
            continue
        rel: dict[str, int] = {}
        for rel_path, text in contents.items():
            if all(t in text for t in terms):
                rel[rel_path] = 1
        qrels[q] = rel
    return qrels


def load_or_build_qrels(
    vault: Path,
    force: bool = False,
    overrides: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, int]]:
    """Load cached qrels if valid for current vault, else rebuild + cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and QRELS_CACHE.exists():
        try:
            cached = json.loads(QRELS_CACHE.read_text(encoding="utf-8"))
            if cached.get("vault") == str(Path(vault).resolve()) and "qrels" in cached:
                return cached["qrels"]
        except (json.JSONDecodeError, OSError):
            # An unreadable or stale cache is intentionally rebuilt below.
            pass
    qrels = build_qrels(vault, overrides=overrides)
    QRELS_CACHE.write_text(
        json.dumps({"vault": str(Path(vault).resolve()), "qrels": qrels}, ensure_ascii=False),
        encoding="utf-8",
    )
    return qrels


def run_search(
    vault: Path,
    queries: list[str],
    mode: str,
    max_results: int = 20,
) -> dict[str, dict[str, int]]:
    """Run search_vault for each query, returning query -> {doc: score}."""
    from power_framework.core.searcher import search_vault

    run: dict[str, dict[str, int]] = {}
    for q in queries:
        results = search_vault(Path(vault), q, max_results=max_results, mode=mode)
        run[q] = {r.rel_path: float(r.score) for r in results}
    return run


def evaluate(
    vault: Path,
    mode: str = "reranked",
    gate: float = 0.50,
    udcg_gate: float = 0.45,
    max_results: int = 20,
    overrides: dict[str, list[str]] | None = None,
    force_qrels: bool = False,
) -> dict[str, float]:
    """Build qrels + run, compute metrics, print, and return the metric dict.

    The legacy lexical proxy is diagnostic only; it is not EACL-2026 UDCG and
    must not be used as a release-quality gate. nDCG@5 remains historical.
    """
    ranx = _ensure_ranx()
    from power_framework.core.metrics.discounted_lexical_gain import (
        normalized_discounted_lexical_gain,
        utilities_from_relevance,
    )

    queries = list((overrides or {}).keys()) or DEFAULT_QUERIES
    qrels = load_or_build_qrels(vault, force=force_qrels, overrides=overrides)
    run = run_search(vault, queries, mode=mode, max_results=max_results)

    # Pre-load doc contents once (for graded-utility / UDCG computation).
    contents: dict[str, str] = {}
    for f in _iter_md_files(Path(vault)):
        try:
            contents[_rel(f, Path(vault))] = f.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:  # noqa: PERF203 - unreadable vault files must not abort the benchmark
            continue

    # ranx wants qrels/run as dict[str, dict[str, int]].
    ranx_qrels = {q: qrels.get(q, {}) for q in queries}
    ranx_run = {q: run.get(q, {}) for q in queries}

    # Drop queries with no GT relevant docs (undefined ndcg/recall/mrr -> skip).
    eval_queries = [q for q in queries if ranx_qrels[q]]
    if not eval_queries:
        print(
            "ERROR: no GT-relevant documents found for any query; cannot compute metrics.",
            file=sys.stderr,
        )
        return {}
    ranx_qrels = {q: ranx_qrels[q] for q in eval_queries}
    ranx_run = {q: ranx_run[q] for q in eval_queries}

    qrels_obj = ranx.Qrels(ranx_qrels)
    run_obj = ranx.Run(ranx_run)
    metrics = ranx.evaluate(
        qrels_obj, run_obj, ["ndcg@5", "recall@5", "mrr@5"], make_comparable=True
    )

    nd = float(metrics["ndcg@5"])
    rc = float(metrics["recall@5"])
    mr = float(metrics["mrr@5"])

    # UDCG@5: per-doc utility = graded relevance (fraction of query terms present)
    # mapped to [0,1]; normalized against the ideal ordering of retrieved utils.
    per_query_udcg: list[float] = []
    for q in eval_queries:
        terms = _tokenize_query(q)
        n_terms = max(len(terms), 1)
        ranked_docs = list(ranx_run[q].keys())[:5]
        utilities: list[float] = []
        for doc in ranked_docs:
            text = contents.get(doc, "")
            matched = sum(1 for t in terms if t in text)
            grade = round(matched / n_terms * 3)  # 0..3 graded relevance
            utilities.extend(utilities_from_relevance([grade], max_relevance=3))
        per_query_udcg.append(normalized_discounted_lexical_gain(utilities, k=5))
    udcg5 = sum(per_query_udcg) / len(per_query_udcg) if per_query_udcg else 0.0

    passed = nd >= gate and udcg5 >= udcg_gate

    print(f"vault   : {vault}")
    print(f"mode    : {mode}")
    print(f"queries : {len(eval_queries)} (with GT relevance)")
    print(f"ndcg@5  : {nd:.4f}   (secondary gate >= {gate:.2f})")
    print(f"udcg@5  : {udcg5:.4f}   (PRIMARY gate >= {udcg_gate:.2f})")
    print(f"recall@5: {rc:.4f}")
    print(f"mrr@5   : {mr:.4f}")
    print(f"gate    : -> {'PASS' if passed else 'FAIL'}")
    return {
        "ndcg@5": nd,
        "udcg@5": udcg5,
        "recall@5": rc,
        "mrr@5": mr,
        "passed": passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POWER search-quality gate.")
    parser.add_argument("--vault", default="/root/gemma/brain", type=str)
    parser.add_argument("--mode", default="reranked", type=str)
    parser.add_argument("--gate", default=0.50, type=float, help="ndcg@5 secondary gate.")
    parser.add_argument("--udcg-gate", default=0.45, type=float, help="UDCG@5 primary gate.")
    parser.add_argument("--max-results", default=20, type=int)
    parser.add_argument(
        "--queries",
        default=None,
        type=str,
        help="Optional JSON file: query -> [rel_doc_rel_paths] overrides.",
    )
    parser.add_argument(
        "--force-qrels", action="store_true", help="Rebuild the qrels cache even if present."
    )
    args = parser.parse_args(argv)

    overrides: dict[str, list[str]] | None = None
    if args.queries:
        overrides = json.loads(Path(args.queries).read_text(encoding="utf-8"))

    metrics = evaluate(
        vault=Path(args.vault),
        mode=args.mode,
        gate=args.gate,
        udcg_gate=args.udcg_gate,
        max_results=args.max_results,
        overrides=overrides,
        force_qrels=args.force_qrels,
    )
    if not metrics:
        return 1
    return 0 if metrics["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
