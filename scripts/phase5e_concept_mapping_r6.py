"""POWER 3.8 Phase 5E R6 — evaluation-only concept identity mapping.

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

import hashlib
from pathlib import Path
from typing import Any

from power_framework.core.evaluation_contracts import load_bounded_json
from power_framework.core.utils import read_file_bytes_no_follow

_MANIFEST_DEFAULT = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
    / "project-state"
    / "phase-5e"
    / "phase5e_runtime_fixture_manifest_r6a1.json"
)


def load_manifest(manifest_path: Path | str = _MANIFEST_DEFAULT) -> dict[str, Any]:
    """Load the immutable R6A.1 manifest and its exact R6 base snapshot."""
    path = Path(manifest_path)
    data = load_bounded_json(path)
    if not isinstance(data, dict):
        raise ValueError("fixture manifest must be a JSON object")
    base_reference = data.get("base_manifest_path")
    if base_reference is None:
        return data
    if (
        not isinstance(base_reference, str)
        or Path(base_reference).name != base_reference
        or Path(base_reference).suffix != ".json"
        or ".." in Path(base_reference).parts
    ):
        raise ValueError("R6A.1 base manifest reference is unsafe")
    base_path = path.parent / base_reference
    base_bytes = read_file_bytes_no_follow(base_path, max_bytes=4 * 1024 * 1024)
    actual_base_digest = hashlib.sha256(base_bytes).hexdigest()
    if actual_base_digest != data.get("base_manifest_sha256"):
        raise ValueError("R6A.1 base manifest digest mismatch")
    base = load_bounded_json(base_path)
    if not isinstance(base, dict):
        raise ValueError("R6 base manifest must be a JSON object")
    merged = dict(base)
    merged.pop("runtime_main_sha", None)
    merged.update({key: value for key, value in data.items() if key != "base_manifest_path"})
    overrides = data.get("concept_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("R6A.1 concept_overrides must be an object")
    concepts = [dict(concept) for concept in merged.get("concepts", [])]
    concepts_by_id = {str(concept.get("eval_concept_id")): concept for concept in concepts}
    for concept_id, override in overrides.items():
        if concept_id not in concepts_by_id or not isinstance(override, dict):
            raise ValueError("R6A.1 concept override is invalid")
        concepts_by_id[concept_id].update(override)
    merged["concepts"] = concepts
    merged["base_manifest_path"] = base_reference
    return merged


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
    """Check if concept is legitimately owner-backed (real runtime ledger)."""
    for concept in manifest.get("concepts", []):
        if concept.get("eval_concept_id") == eval_concept_id:
            return bool(concept.get("owner_backed", False))
    return False


def get_setup_payload(
    eval_concept_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Return setup_payload for a concept (or None)."""
    for concept in manifest.get("concepts", []):
        if concept.get("eval_concept_id") == eval_concept_id:
            payload = concept.get("setup_payload")
            return dict(payload) if isinstance(payload, dict) else None
    return None
