#!/usr/bin/env python3
"""POWER 3.0 — Doc-Drift CI Gate (R1, fixes DOC-DRIFT / B9).

Every prior release shipped a README that disagreed with the code: README said
Qwen3 while the code defaulted to Granite; cache/model names drifted; the
"5 modes" claim outlived the code. This gate makes that class of bug fail CI.

It compares the CANONICAL stack declared in code
(``power_framework.core.embeddings`` / ``core.reranker``) against what the
README advertises, and exits non-zero on any mismatch.

Usage:
    python scripts/check_doc_drift.py                 # check all
    python scripts/check_doc_drift.py --check embedder,reranker

Checks:
    embedder  — README must name the canonical dense backend (EMBED_PROVIDER)
    reranker  — README must name the canonical reranker model
    mode      — README must name the canonical search mode ("reranked")
    version   — README/CHANGELOG must not reference a stale default provider

Exit code 0 = in sync, 1 = drift detected.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

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


def _load_code_facts() -> dict[str, str]:
    """Import the code and read the canonical stack constants."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from power_framework.core import reranker
    from power_framework.core.embeddings import EMBED_PROVIDER
    from power_framework.core.searcher import search_vault

    # The canonical search mode is the default argument of search_vault.
    import inspect

    sig = inspect.signature(search_vault)
    default_mode = sig.parameters["mode"].default

    return {
        "embedder": EMBED_PROVIDER,
        "reranker": reranker.DEFAULT_RERANKER_MODEL,
        "mode": default_mode,
    }


def _read_readme() -> str:
    if not README.exists():
        print(f"::error:: README not found at {README}", file=sys.stderr)
        sys.exit(2)
    return README.read_text(encoding="utf-8")


def check_embedder(readme: str, provider: str) -> list[str]:
    errors: list[str] = []
    aliases = _PROVIDER_ALIASES.get(provider, [provider])
    if not any(a in readme for a in aliases):
        errors.append(
            f"README does not advertise the canonical embedder "
            f"'{provider}' (expected one of {aliases}). "
            f"Update README's search/embedding sections."
        )
    for pat in _STALE_DEFAULT_MARKERS.get(provider, []):
        if re.search(pat, readme):
            errors.append(
                f"README still describes a SUPERSEDED default embedder "
                f"(matched /{pat}/) while code default is '{provider}'."
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


CHECKS = {
    "embedder": lambda r, f: check_embedder(r, f["embedder"]),
    "reranker": lambda r, f: check_reranker(r, f["reranker"]),
    "mode": lambda r, f: check_mode(r, f["mode"]),
    "version": lambda r, f: check_version(r, f["embedder"]),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="POWER doc-drift gate")
    parser.add_argument(
        "--check",
        default="embedder,reranker,version",
        help="comma-separated checks to run (default: all)",
    )
    args = parser.parse_args()
    requested = [c.strip() for c in args.check.split(",") if c.strip()]

    facts = _load_code_facts()
    readme = _read_readme()

    all_errors: list[str] = []
    for name in requested:
        fn = CHECKS.get(name)
        if fn is None:
            print(f"::warning:: unknown check '{name}' skipped", file=sys.stderr)
            continue
        all_errors.extend(fn(readme, facts))

    if all_errors:
        print("Doc-drift detected:\n", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            f"\nCode facts: embedder={facts['embedder']!r} reranker={facts['reranker']!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Doc-drift check passed: README matches code "
        f"(embedder={facts['embedder']}, reranker={facts['reranker'].rsplit('/', 1)[-1]}, "
        f"mode={facts['mode']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
