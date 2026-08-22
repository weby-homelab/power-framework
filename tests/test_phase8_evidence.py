"""Fail-closed tests for the external Phase 8 release evidence contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_phase8_evidence.py"
SPEC = importlib.util.spec_from_file_location("phase8_evidence", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
phase8 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase8)


def _valid_real_receipt(human_hash: str) -> dict[str, object]:
    return {
        "schema_version": "power.phase8.real-vault-receipt.v1",
        "release": "3.5.0",
        "status": "passed",
        "content_free": True,
        "raw_content_present": False,
        "source": {"revision": "a" * 40, "clean": True},
        "vault": {"opaque_id": "vault-opaque", "snapshot_sha256": "b" * 64, "note_count": 733},
        "runtime": {
            "executable": "/opt/power/bin/power",
            "provider": "cpu",
            "generation": "generation-42",
            "config_sha256": "c" * 64,
        },
        "experiments": [
            {"id": name, "status": "passed", "receipt_sha256": "d" * 64}
            for name in ("build", "transfer", "import", "query")
        ],
        "quality": {
            "sealed_dataset": True,
            "real_vault": True,
            "blind_scoring": True,
            "no_answer_scoring": True,
            "outcome_gate": "pass",
            "power_beats_no_power": True,
            "comparators": ["fts", "auto", "semantic", "no_power"],
            "metrics": {
                "recall_at_10": 0.9,
                "ndcg_at_10": 0.9,
                "mrr_at_10": 0.9,
                "evidence_use": 0.9,
                "no_answer_score": 0.9,
                "stale_answer_rate": 0.01,
                "latency_p95_ms": 100.0,
            },
            "fresh_agent_completion_percent": 95,
            "safety_invariants_percent": 100,
            "median_human_reminders": 0,
        },
        "human_evidence": {
            "status": "passed",
            "sealed_holdout": True,
            "manifest_sha256": human_hash,
        },
    }


def _write_human_manifest(path: Path, *, status: str = "adjudicated") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "status": status,
                "split": "sealed_holdout",
                "language": "uk",
                "corpus_sha256": "a" * 64,
                "queries_sha256": "b" * 64,
                "raw_judgments_sha256": "c" * 64,
                "adjudicated_qrels_sha256": "d" * 64,
                "artifacts": {
                    "corpus": "corpus.jsonl",
                    "queries": "queries.jsonl",
                    "raw_judgments": "raw.jsonl",
                    "adjudicated_qrels": "qrels.jsonl",
                },
                "annotation_protocol": "annotation_protocol_v2.md",
                "calibration": {"status": "pending"},
                "threshold_profile": "m2-v2.1",
                "journeys": [
                    "current_fact",
                    "historical_fact",
                    "provenance_trace",
                    "abstention",
                    "candidate_boundary",
                ],
                "thresholds": {"placeholder": True},
            }
        ),
        encoding="utf-8",
    )


def test_real_receipt_requires_all_four_experiments() -> None:
    receipt = _valid_real_receipt("e" * 64)
    receipt["experiments"] = []

    errors = phase8.validate_real_vault_receipt(receipt, release="3.5.0")

    assert any("build, transfer, import and query" in error for error in errors)


def test_technical_receipts_are_content_free_and_complete(tmp_path: Path) -> None:
    release = "3.7.1"
    source_commit = "a" * 40
    source_tree = "b" * 40
    worktree_sha256 = "c" * 64
    source = {
        "commit": source_commit,
        "tree": source_tree,
        "clean": False,
        "worktree_sha256": worktree_sha256,
    }
    outcome = tmp_path / "outcome.json"
    continuity = tmp_path / "continuity.json"
    outcome.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8-outcome.v2",
                "release": release,
                "source": source,
                "synthetic": True,
                "content_free": True,
                "workflow_count": 20,
                "gate": {
                    "fresh_agent_completion": 1.0,
                    "safety_invariants_100": True,
                    "false_premise_abstention": True,
                    "stale_state_filter": True,
                    "technical_continuity_20": True,
                    "blocked_workflow_abstention": True,
                    "median_human_reminders": 0,
                },
                "comparison": {
                    "practical_improvement": True,
                    "power_mean_score": 0.95,
                    "no_power_mean_score": 0.35,
                    "evidence_recall": {"power": 0.75, "no_power": 0.0},
                },
                "feedback_reuse": {
                    "measured": False,
                    "reason": "no human labels",
                },
                "retrieval_profiles": {
                    "fts": {"status": "executed"},
                    "auto": {"status": "executed"},
                    "semantic": {
                        "status": "not_evaluated",
                        "reason": "no sealed provider",
                    },
                },
                "blind_scoring": False,
                "bootstrap_context_tokens": {"measured": False},
                "raw_content_in_report": False,
                "human_quality_certification": False,
                "real_vault": False,
                "sealed_holdout": "not_opened",
            }
        ),
        encoding="utf-8",
    )
    continuity.write_text(
        json.dumps(
            {
                "schema_version": "power.phase8-continuity.v2",
                "release": release,
                "source": source,
                "synthetic": True,
                "content_free": True,
                "workflow_count": 20,
                "independent_processes": 60,
                "plain_handoff_processes": 40,
                "metrics": {"duplicate_work_rate": 0.0},
                "gate": {
                    "correct_resume_20": True,
                    "proof_carrying_handoff": True,
                    "source_preserved": True,
                    "unsafe_actions_100_percent_safe": True,
                    "human_reminders_median_zero": True,
                    "power_beats_plain_handoff": True,
                },
                "comparison": {
                    "practical_improvement": True,
                    "power_continuity_rate": 1.0,
                    "plain_handoff_continuity_rate": 0.0,
                },
                "raw_content_in_report": False,
                "human_quality_certification": False,
                "real_vault": False,
                "sealed_holdout": "not_opened",
            }
        ),
        encoding="utf-8",
    )

    assert (
        phase8.validate_technical_receipts(
            outcome_path=outcome,
            continuity_path=continuity,
            release=release,
            source_commit=source_commit,
            source_tree=source_tree,
            worktree_sha256=worktree_sha256,
        )
        == []
    )


def test_technical_receipts_reject_stale_release_or_source(tmp_path: Path) -> None:
    outcome = tmp_path / "outcome.json"
    continuity = tmp_path / "continuity.json"
    source = {
        "commit": "a" * 40,
        "tree": "b" * 40,
        "clean": True,
        "worktree_sha256": "c" * 64,
    }
    for path, schema in (
        (outcome, "power.phase8-outcome.v2"),
        (continuity, "power.phase8-continuity.v2"),
    ):
        path.write_text(
            json.dumps({"schema_version": schema, "release": "3.5.0", "source": source}),
            encoding="utf-8",
        )

    errors = phase8.validate_technical_receipts(
        outcome_path=outcome,
        continuity_path=continuity,
        release="3.7.1",
        source_commit="d" * 40,
        source_tree="e" * 40,
        require_clean=True,
    )

    assert any("release must be 3.7.1" in error for error in errors)
    assert any("source.commit" in error for error in errors)
    assert any("source.tree" in error for error in errors)


def test_phase8_json_hash_is_stable_for_crlf_manifest(tmp_path: Path) -> None:
    lf = tmp_path / "manifest-lf.json"
    crlf = tmp_path / "manifest-crlf.json"
    payload = '{"status":"adjudicated"}\n'
    lf.write_text(payload, encoding="utf-8", newline="")
    crlf.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))

    assert phase8._canonical_file_sha256(lf) == phase8._canonical_file_sha256(crlf)


def test_real_receipt_rejects_unblinded_or_non_improving_claim() -> None:
    receipt = _valid_real_receipt("e" * 64)
    quality = receipt["quality"]
    assert isinstance(quality, dict)
    quality["blind_scoring"] = False
    quality["power_beats_no_power"] = False

    errors = phase8.validate_real_vault_receipt(receipt, release="3.5.0")

    assert any("blind_scoring" in error for error in errors)
    assert any("power_beats_no_power" in error for error in errors)


def test_real_receipt_reports_malformed_numeric_and_comparator_fields() -> None:
    receipt = _valid_real_receipt("e" * 64)
    quality = receipt["quality"]
    assert isinstance(quality, dict)
    quality["comparators"] = [{"unexpected": "object"}]
    quality["fresh_agent_completion_percent"] = "ninety"

    errors = phase8.validate_real_vault_receipt(receipt, release="3.5.0")

    assert any("must cover FTS" in error for error in errors)
    assert any("fresh_agent_completion_percent" in error for error in errors)


def test_phase8_validation_rejects_non_adjudicated_human_manifest(tmp_path: Path) -> None:
    human = tmp_path / "human.json"
    _write_human_manifest(human, status="pending_calibration")
    real = tmp_path / "real.json"
    real.write_text(
        json.dumps(_valid_real_receipt(hashlib.sha256(human.read_bytes()).hexdigest())),
        encoding="utf-8",
    )

    errors = phase8.validate_phase8_evidence(
        real_vault_receipt_path=real,
        human_manifest_path=human,
        release="3.5.0",
    )

    assert any("human manifest status must be adjudicated" in error for error in errors)


def test_phase8_validation_fails_closed_when_receipts_are_missing(tmp_path: Path) -> None:
    errors = phase8.validate_phase8_evidence(
        real_vault_receipt_path=tmp_path / "missing-real.json",
        human_manifest_path=tmp_path / "missing-human.json",
        release="3.5.0",
    )

    assert len(errors) == 2
    assert all("missing or invalid JSON" in error for error in errors)


def test_phase8_validation_accepts_formatted_human_manifest_hash(tmp_path: Path) -> None:
    human = tmp_path / "human.json"
    _write_human_manifest(human, status="adjudicated")
    manifest_obj = json.loads(human.read_text(encoding="utf-8"))
    pretty_bytes = json.dumps(manifest_obj, indent=2).encode("utf-8") + b"\n"
    pretty_hash = hashlib.sha256(pretty_bytes).hexdigest()

    candidates = phase8._candidate_manifest_hashes(human, manifest_obj)
    assert pretty_hash in candidates


def test_phase8_validation_accepts_standard_python_dumps_hash(tmp_path: Path) -> None:
    """Standard json.dumps (with spaces after : and ,) must also be a candidate hash."""
    human = tmp_path / "human.json"
    _write_human_manifest(human, status="adjudicated")
    manifest_obj = json.loads(human.read_text(encoding="utf-8"))
    # Standard json.dumps produces {"key": "val"} with spaces — not covered by compact separators
    for trailing in (b"\n", b""):
        for sort in (False, True):
            std_bytes = (
                json.dumps(manifest_obj, ensure_ascii=False, sort_keys=sort).encode("utf-8")
                + trailing
            )
            std_hash = hashlib.sha256(std_bytes).hexdigest()
            candidates = phase8._candidate_manifest_hashes(human, manifest_obj)
            assert std_hash in candidates, (
                f"Standard json.dumps hash missing (sort={sort}, trailing={bool(trailing)})"
            )


def test_phase8_validation_accepts_ascii_escaped_unicode_hash(tmp_path: Path) -> None:
    """Default JSON escaping must be accepted for manifests containing Ukrainian text."""
    human = tmp_path / "human.json"
    _write_human_manifest(human, status="adjudicated")
    manifest_obj = json.loads(human.read_text(encoding="utf-8"))
    manifest_obj["annotation_protocol"] = "протокол_ua.md"

    escaped_bytes = json.dumps(manifest_obj, indent=2, ensure_ascii=True).encode("utf-8") + b"\n"
    escaped_hash = hashlib.sha256(escaped_bytes).hexdigest()

    assert escaped_hash in phase8._candidate_manifest_hashes(human, manifest_obj)
