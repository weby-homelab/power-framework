"""POWER 3.8 Phase 5E R5 — evaluation-only concept identity mapping.

RUNTIME != BENCHMARK.

This module maps different runtime representations (Markdown file stems and
canonical runtime IDs like ``task:<id>`` / ``decision:<id>`` /
``project:<id>``) to a single ``eval_concept_id`` for scoring ONLY.

The mapping NEVER enters RetrievalPlanner, NEVER changes ranking, NEVER
grants authority, and NEVER reaches ApplicationService input. It exists only
after retrieval for scoring, so Legacy and Shadow are evaluated on identical
semantic concepts even when they return different representations.

Ground truth scores output; ground truth never produces output.
TEXT != AUTHORITY, TAG != AUTHORITY, PATH != AUTHORITY, DOMAIN != AUTHORITY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MANIFEST_DEFAULT = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
    / "project-state"
    / "phase-5e"
    / "phase5e_runtime_fixture_manifest_r5.json"
)


def load_manifest(manifest_path: Path | str = _MANIFEST_DEFAULT) -> dict[str, Any]:
    """Load the frozen R5 fixture manifest (read-only)."""
    with Path(manifest_path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_raw_source_id(raw_id: str) -> str:
    """Normalize a retrieved source_id to a comparable stem.

    Handles canonical runtime prefixes ``task:`` / ``decision:`` /
    ``project:`` plus filesystem paths (takes stem). Pure evaluation
    helper; never used by production retrieval.
    """
    cleaned = str(raw_id).removeprefix("task:").removeprefix("decision:").removeprefix("project:")
    return Path(cleaned).stem


def build_alias_to_concept(
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Build alias -> eval_concept_id lookup from manifest scoring_aliases."""
    lookup: dict[str, str] = {}
    for concept in manifest.get("concepts", []):
        cid = concept.get("eval_concept_id", "")
        for alias in concept.get("scoring_aliases", []):
            lookup[str(alias)] = cid
            # Also index the normalized stem for filesystem-prefixed hits.
            lookup[_normalize_raw_source_id(str(alias))] = cid
    return lookup


def source_id_to_concept(
    raw_source_id: str,
    alias_lookup: dict[str, str],
) -> str | None:
    """Map one retrieved source_id to its eval_concept_id (or None)."""
    if raw_source_id in alias_lookup:
        return alias_lookup[raw_source_id]
    stem = _normalize_raw_source_id(raw_source_id)
    return alias_lookup.get(stem)


def concept_to_aliases(
    eval_concept_id: str,
    manifest: dict[str, Any],
) -> list[str]:
    """Return all scoring aliases for one concept."""
    for concept in manifest.get("concepts", []):
        if concept.get("eval_concept_id") == eval_concept_id:
            return list(concept.get("scoring_aliases", []))
    return []


def owner_for_concept(
    eval_concept_id: str,
    manifest: dict[str, Any],
) -> str:
    """Return production_owner for a concept (default VaultNote)."""
    for concept in manifest.get("concepts", []):
        if concept.get("eval_concept_id") == eval_concept_id:
            return str(concept.get("production_owner", "VaultNote"))
    return "VaultNote"


def is_owner_backed(
    eval_concept_id: str,
    manifest: dict[str, Any],
) -> bool:
    """True only for TaskService / DecisionService / ProjectStateService with active runtime object."""
    for concept in manifest.get("concepts", []):
        if concept.get("eval_concept_id") == eval_concept_id:
            return (
                bool(concept.get("owner_backed", False))
                and concept.get("production_owner") in {
                    "TaskService",
                    "DecisionService",
                    "ProjectStateService",
                }
                and bool(concept.get("runtime_object_id"))
            )
    return False
