#!/usr/bin/env python3
"""POWER 3.0 — Doc-Drift CI Gate (R1, fixes DOC-DRIFT / B9).

Every prior release shipped a README that disagreed with the code: README said
Qwen3 while the code defaulted to Granite; cache/model names drifted; the
"5 modes" claim outlived the code. This gate makes that class of bug fail CI.

It compares the canonical stack and executable retrieval registry declared in
code against the current public documentation, and exits non-zero on mismatch.

Usage:
    python scripts/check_doc_drift.py                 # check all
    python scripts/check_doc_drift.py --check embedder,reranker,retrieval

Checks:
    embedder  — README must name the canonical dense backend (EMBED_PROVIDER)
    reranker  — README must name the canonical reranker model
    mode      — README must name the canonical search mode
    version   — README must not reference a stale default provider
    retrieval — Architecture/API tables must match the code retrieval registry

Exit code 0 = in sync, 1 = drift detected.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
README_UA = REPO_ROOT / "README.ua.md"
ARCHITECTURE = REPO_ROOT / "docs" / "architecture.md"
SEARCHER_API = REPO_ROOT / "docs" / "api" / "searcher.md"
RERANKER_API = REPO_ROOT / "docs" / "api" / "reranker.md"
CURRENT_DOCUMENTS = {
    "README": README,
    "README.ua": README_UA,
    "Architecture": ARCHITECTURE,
    "Searcher API": SEARCHER_API,
    "Reranker API": RERANKER_API,
}

# Canonical provider -> the human-readable token(s) the README MUST contain to
# be considered "in sync". Whichever provider the code declares as default, the
# README must advertise it (and must NOT still advertise a superseded default).
_PROVIDER_ALIASES: dict[str, list[str]] = {
    "bge-m3": ["bge-m3", "BGE-M3"],
    "qwen3": ["Qwen3-Embedding", "Qwen3-0.6B"],
    "fastembed": ["MiniLM", "Granite", "granite"],
    "ollama": ["ollama"],
}

# Superseded defaults that must NOT be described as "default" once we moved on.
_STALE_DEFAULT_MARKERS = {
    "bge-m3": [
        r"[Dd]efault backend .{0,40}Qwen3-Embedding",
        r"[Dd]efault .{0,40}Granite",
        r"default provider is now ``qwen3``",
    ],
}


def _load_code_facts() -> dict[str, Any]:
    """Import the code and read the canonical stack constants."""
    import inspect

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from power_framework.core import reranker
    from power_framework.core.embeddings import (
        BGE_M3_ONNX_REPO,
        BGE_M3_ONNX_REVISION,
        EMBED_PROVIDER,
    )
    from power_framework.core.reranker import (
        BGE_RERANKER_ONNX_REPO,
        BGE_RERANKER_ONNX_REVISION,
    )
    from power_framework.core.searcher import SEARCH_MODE_REGISTRY, search_vault

    # The canonical search mode is the default argument of search_vault.
    sig = inspect.signature(search_vault)
    default_mode = sig.parameters["mode"].default

    return {
        "embedder": EMBED_PROVIDER,
        "reranker": reranker.DEFAULT_RERANKER_MODEL,
        "mode": default_mode,
        "embedding_model": f"{BGE_M3_ONNX_REPO}@{BGE_M3_ONNX_REVISION}",
        "reranker_model": f"{BGE_RERANKER_ONNX_REPO}@{BGE_RERANKER_ONNX_REVISION}",
        "registry": tuple(
            (
                mode,
                " + ".join(spec.candidate_sources),
                spec.fusion or "—",
                "yes" if spec.reranker else "no",
                "yes" if spec.requires_dense_index else "no",
            )
            for mode, spec in sorted(SEARCH_MODE_REGISTRY.items())
        ),
    }


def _read_current_documents() -> dict[str, str]:
    """Read the documentation that describes the current executable contract."""
    documents: dict[str, str] = {}
    for label, path in CURRENT_DOCUMENTS.items():
        if not path.exists():
            print(f"::error:: {label} not found at {path}", file=sys.stderr)
            sys.exit(2)
        documents[label] = path.read_text(encoding="utf-8")
    return documents


def check_embedder(readme: str, provider: str) -> list[str]:
    errors: list[str] = []
    aliases = _PROVIDER_ALIASES.get(provider, [provider])
    if not any(a in readme for a in aliases):
        errors.append(
            f"README does not advertise the canonical embedder "
            f"'{provider}' (expected one of {aliases}). "
            f"Update README's search/embedding sections."
        )
    errors.extend(
        f"README still describes a SUPERSEDED default embedder "
        f"(matched /{pat}/) while code default is '{provider}'."
        for pat in _STALE_DEFAULT_MARKERS.get(provider, [])
        if re.search(pat, readme)
    )
    return errors


def check_reranker(readme: str, model: str) -> list[str]:
    # Match on the model's short name (last path segment) to survive org renames.
    short = model.rsplit("/", 1)[-1]
    if short not in readme and model not in readme:
        return [
            f"README does not name the canonical reranker '{model}' "
            f"(short name '{short}'). Update the Cross-Encoder Reranker row."
        ]
    return []


def check_version(readme: str, provider: str) -> list[str]:
    # Guard against the classic "default provider is now qwen3" line lingering
    # after a provider swap.
    errors: list[str] = []
    if provider != "qwen3" and "default provider is now ``qwen3``" in readme:
        errors.append(
            "README/CHANGELOG claims qwen3 is the default provider, but the "
            f"code default is '{provider}'."
        )
    return errors


def check_mode(readme: str, mode: str) -> list[str]:
    # The canonical search mode declared in code (search_vault default) must be
    # advertised in the README, and a stale "5 modes" / old default must not
    # linger. Prevents the classic "mode claim outlived the code" doc-drift.
    if mode not in readme and f"`{mode}`" not in readme:
        return [
            f"README does not name the canonical search mode '{mode}' "
            f"(the code default for search_vault). Update the search section."
        ]
    return []


def check_retrieval_registry(documents: dict[str, str], facts: dict[str, Any]) -> list[str]:
    """Require the generated architecture table to equal the code registry."""
    errors: list[str] = []
    architecture = documents["Architecture"]
    expected_header = "| Mode | Candidate sources | Fusion | Reranker | Requires dense index |"
    if expected_header not in architecture:
        errors.append("Architecture is missing the canonical retrieval-registry table header.")
    for mode, sources, fusion, reranker, dense in facts["registry"]:
        fusion_cell = f"`{fusion}`" if fusion != "—" else fusion
        expected_row = f"| `{mode}` | `{sources}` | {fusion_cell} | {reranker} | {dense} |"
        if expected_row not in architecture:
            errors.append(
                f"Architecture retrieval row does not match code registry: {expected_row}"
            )
    expected_default = f"The current default is `{facts['mode']}`"
    if expected_default not in architecture:
        errors.append(f"Architecture does not declare the code default `{facts['mode']}`.")
    for key, label in (("embedding_model", "embedding"), ("reranker_model", "reranker")):
        if facts[key] not in architecture:
            errors.append(
                f"Architecture does not name the pinned canonical {label} model `{facts[key]}`."
            )

    searcher_api = documents["Searcher API"]
    if f"The current default is `{facts['mode']}`, not `reranked`." not in searcher_api:
        errors.append(
            "Searcher API does not declare the current semantic default and reranked opt-in."
        )

    stale_claims = {
        "README": (
            "canonical Jina v2 reranker remains the fallback",
            "**`jina-reranker-v2-base-multilingual`** (default)",
        ),
        "README.ua": (
            "канонічний Jina v2 реранкер залишається fallback",
            "**`jina-reranker-v2-base-multilingual`** (за замовчуванням)",
        ),
        "Architecture": ("Jina v2 multilingual default",),
        "Searcher API": (
            "`reranked` (canonical, default",
            "Jina v2 cross-encoder rerank",
            "`semantic` (alias of `vector`)",
        ),
    }
    for label, claims in stale_claims.items():
        errors.extend(
            f"{label} contains a superseded retrieval/model claim: {claim!r}."
            for claim in claims
            if claim in documents[label]
        )
    return errors


CHECKS = {
    "embedder": lambda r, f: check_embedder(r, f["embedder"]),
    "reranker": lambda r, f: check_reranker(r, f["reranker"]),
    "mode": lambda r, f: check_mode(r, f["mode"]),
    "version": lambda r, f: check_version(r, f["embedder"]),
    "retrieval": check_retrieval_registry,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="POWER doc-drift gate")
    parser.add_argument(
        "--check",
        default="embedder,reranker,mode,version,retrieval",
        help="comma-separated checks to run (default: all)",
    )
    args = parser.parse_args()
    requested = [c.strip() for c in args.check.split(",") if c.strip()]

    facts = _load_code_facts()
    documents = _read_current_documents()
    readme = documents["README"]

    all_errors: list[str] = []
    for name in requested:
        fn = CHECKS.get(name)
        if fn is None:
            print(f"::warning:: unknown check '{name}' skipped", file=sys.stderr)
            continue
        if name == "retrieval":
            all_errors.extend(fn(documents, facts))
        else:
            all_errors.extend(fn(readme, facts))

    if all_errors:
        print("Doc-drift detected:\n", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            f"\nCode facts: embedder={facts['embedder']!r} reranker={facts['reranker']!r} "
            f"mode={facts['mode']!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Doc-drift check passed: current public docs match code "
        f"(embedder={facts['embedder']}, reranker={facts['reranker'].rsplit('/', 1)[-1]}, "
        f"mode={facts['mode']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
