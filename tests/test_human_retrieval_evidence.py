"""Contract tests for the M2 human-evidence boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "validate_human_evidence.py"
)
SPEC = importlib.util.spec_from_file_location("m2_evidence", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifest(**overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "status": "pending_human_annotation",
        "split": "development",
        "corpus_sha256": "a" * 64,
        "queries_sha256": "b" * 64,
        "raw_judgments_sha256": "c" * 64,
        "adjudicated_qrels_sha256": "d" * 64,
        "artifacts": {
            "corpus": "corpus.jsonl",
            "queries": "queries.jsonl",
            "raw_judgments": "raw-judgments.jsonl",
            "adjudicated_qrels": "adjudicated-qrels.jsonl",
        },
        "journeys": sorted(MODULE.REQUIRED_JOURNEYS),
        "thresholds": None,
    }
    manifest.update(overrides)
    return manifest


def test_development_manifest_is_valid_before_annotation() -> None:
    assert MODULE.validate_manifest(_manifest(), allow_sealed=False) == []


def test_sealed_holdout_requires_explicit_release_review() -> None:
    manifest = _manifest(split="sealed_holdout")
    assert "sealed_holdout requires --allow-sealed" in MODULE.validate_manifest(
        manifest, allow_sealed=False
    )
    assert MODULE.validate_manifest(manifest, allow_sealed=True) == []


def test_adjudicated_manifest_requires_preregistered_thresholds() -> None:
    errors = MODULE.validate_manifest(_manifest(status="adjudicated"), allow_sealed=False)
    assert "adjudicated evidence requires complete pre-registered thresholds" in errors


def test_evidence_file_binds_each_artifact_to_its_declared_hash(tmp_path: Path) -> None:
    artifacts = _manifest()["artifacts"]
    assert isinstance(artifacts, dict)
    manifest = _manifest()
    for key, filename in artifacts.items():
        content = f"{key}\n"
        (tmp_path / filename).write_text(content, encoding="utf-8")
        manifest[f"{key}_sha256" if key != "raw_judgments" else "raw_judgments_sha256"] = (
            hashlib.sha256(content.encode()).hexdigest()
        )
    manifest["adjudicated_qrels_sha256"] = hashlib.sha256(
        (tmp_path / artifacts["adjudicated_qrels"]).read_bytes()
    ).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert MODULE.validate_evidence_file(manifest_path, allow_sealed=False) == []
    (tmp_path / artifacts["queries"]).write_text("tampered\n", encoding="utf-8")
    assert "queries SHA-256 does not match queries_sha256" in MODULE.validate_evidence_file(
        manifest_path, allow_sealed=False
    )
